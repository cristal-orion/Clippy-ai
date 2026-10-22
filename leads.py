"""
Privacy notice and leads for Clippy bots.

* Privacy: a bot can require visitors to accept a short notice before chatting.
  Each acceptance is recorded as a ConsentEvent (date and a hash of the exact
  notice shown, no IP); changing the notice changes the hash, so visitors are
  asked again.
* Leads: interactive-UI bots with lead recipients show a contact form. Leads
  are stored in Clippy first, then emailed through form-relay
  (moduli.twobee.it) using its token-authenticated "clippy" site, the only kind
  of form-relay site allowed to choose recipients per request.
"""

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_active_user
from database import SessionLocal, get_db
from models import ClippyConfig, ConsentEvent, Lead, User
from openui import leads_on
from schemas import _EMAIL_RE, normalise_lead_emails

router = APIRouter()

FORM_RELAY_URL = os.getenv("FORM_RELAY_URL", "https://moduli.twobee.it").rstrip("/")
FORM_RELAY_SITE = os.getenv("FORM_RELAY_SITE", "clippy")
FORM_RELAY_TOKEN = os.getenv("FORM_RELAY_TOKEN", "")

# Defaults used when a bot leaves a text empty. They are a starting point: the
# texts should be checked against each client's privacy policy.
DEFAULT_PRIVACY_TEXT = (
    "Questa chat usa un assistente basato sull'intelligenza artificiale. I messaggi "
    "e i documenti che invii vengono elaborati, anche da fornitori di servizi AI, "
    "solo per risponderti. Non inserire dati sensibili (salute, dati bancari, "
    "password). Proseguendo dichiari di aver letto l'informativa privacy."
)
DEFAULT_PRIVACY_BUTTON = "Accetto e inizio la chat"
DEFAULT_LEAD_CONSENT = (
    "Acconsento al trattamento dei miei dati e del riepilogo di questa conversazione "
    "per essere ricontattato, come descritto nell'informativa privacy."
)

# Leads and consent records are deleted automatically after each bot's
# retention period (data_retention_days); the sweep runs every 6 hours.
DEFAULT_RETENTION_DAYS = 90
RETENTION_SWEEP_SECONDS = int(os.getenv("RETENTION_SWEEP_SECONDS", "21600"))

LEAD_LABELS = {
    "nome": "Nome e cognome",
    "azienda": "Azienda",
    "email": "Email",
    "telefono": "Telefono",
    "note": "Esigenza",
    "conversazione": "Messaggi del visitatore in chat",
    "consenso": "Consenso al trattamento",
}
LEAD_ORDER = list(LEAD_LABELS)

PHONE_RE = re.compile(r"^[+0-9 ()./-]{6,40}$")


# ============ Helpers shared with main.py ============

def get_client_ip(req: Request) -> str:
    """The visitor's IP. Behind Traefik the TCP peer is the proxy, so the first
    X-Forwarded-For entry is used when the peer is a private address."""
    peer = req.client.host if req.client else ""
    forwarded = req.headers.get("x-forwarded-for", "")
    try:
        if forwarded and ipaddress.ip_address(peer).is_private:
            return forwarded.split(",")[0].strip()[:64]
    except ValueError:
        pass
    return peer


def origin_allowed(config: ClippyConfig, req: Request) -> bool:
    """The bot's domain whitelist, if any, against the page's Origin/Referer."""
    if not config.allowed_domains:
        return True
    allowed = json.loads(config.allowed_domains)
    if not allowed:
        return True
    origin = req.headers.get("origin") or req.headers.get("referer") or ""
    host = urlparse(origin).hostname or ""
    return not host or any(host == d or host.endswith("." + d) for d in allowed)


def privacy_settings(config: ClippyConfig) -> dict:
    """The notice as the widget shows it, with defaults filled in."""
    text = (config.privacy_text or "").strip() or DEFAULT_PRIVACY_TEXT
    url = (config.privacy_policy_url or "").strip()
    button = (config.privacy_button_label or "").strip() or DEFAULT_PRIVACY_BUTTON
    version = hashlib.sha256(f"{text}\n{url}\n{button}".encode()).hexdigest()[:16]
    return {"enabled": bool(config.privacy_enabled), "text": text, "policy_url": url, "button_label": button, "version": version}


def lead_consent_text(config: ClippyConfig) -> str:
    return (config.lead_consent_text or "").strip() or DEFAULT_LEAD_CONSENT


def widget_privacy(config: ClippyConfig) -> dict:
    return privacy_settings(config) if config.privacy_enabled else {"enabled": False}


def widget_leads(config: ClippyConfig) -> dict:
    if not leads_on(config):
        return {"enabled": False}
    return {"enabled": True, "consent_text": lead_consent_text(config), "policy_url": (config.privacy_policy_url or "").strip()}


def consent_valid(db: Session, config: ClippyConfig, consent_id: Optional[str]) -> bool:
    """True when the visitor accepted the bot's current notice."""
    if not consent_id or len(consent_id) > 36:
        return False
    event = db.query(ConsentEvent).filter(ConsentEvent.id == consent_id, ConsentEvent.config_id == config.id).first()
    return bool(event) and event.text_version == privacy_settings(config)["version"]


class _SlidingWindow:
    """In-memory rate limit: at most `limit` hits per key in `seconds`."""

    def __init__(self):
        self.hits = {}

    def allow(self, key: str, limit: int, seconds: int) -> bool:
        now = time.monotonic()
        recent = [t for t in self.hits.get(key, []) if now - t < seconds]
        if len(recent) >= limit:
            self.hits[key] = recent
            return False
        recent.append(now)
        self.hits[key] = recent
        if len(self.hits) > 10000:  # drop idle keys
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 3600}
        return True


_limits = _SlidingWindow()


def _single_line(value: Optional[str], max_len: int) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:max_len]


def _page_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value)
    return value[:500] if parsed.scheme in ("http", "https") and parsed.netloc else None


def _bot_name(config_or_name) -> str:
    if isinstance(config_or_name, str):
        return _single_line(config_or_name, 60) or "Clippy"
    return _single_line(config_or_name.name or config_or_name.agent, 60) or "Clippy"


def _recipients(emails: Optional[str]) -> List[str]:
    return [e.strip() for e in (emails or "").split(",") if e.strip()]


# ============ Delivery through form-relay ============

async def deliver_lead(*, fields: dict, recipients: List[str], bot_name: str, page_url: Optional[str], test: bool = False):
    """Email a lead through form-relay. Returns (status, error)."""
    if not recipients:
        return "not_configured", "nessun destinatario configurato"
    if not FORM_RELAY_TOKEN:
        return "not_configured", "FORM_RELAY_TOKEN non impostato sul server di Clippy"
    payload = {
        "to": [{"email": e} for e in recipients],
        "subject": ("[PROVA] " if test else "") + f"Nuovo contatto da {bot_name} — {{{{nome}}}}",
        "fromName": f"{bot_name} · Clippy"[:70],
        "sourceLabel": bot_name,
        "fields": {k: v for k, v in fields.items() if v},
        "labels": LEAD_LABELS,
        "order": LEAD_ORDER,
        "meta": {"page": page_url} if page_url else {},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{FORM_RELAY_URL}/s/{FORM_RELAY_SITE}",
                json=payload,
                headers={"Authorization": f"Bearer {FORM_RELAY_TOKEN}"},
            )
    except httpx.HTTPError as e:
        return "failed", f"form-relay non raggiungibile ({type(e).__name__})"
    if res.status_code == 200:
        return "sent", None
    try:
        message = res.json().get("message", "")
    except ValueError:
        message = ""
    return "failed", f"form-relay HTTP {res.status_code} {message}".strip()[:300]


def _email_fields(lead: Lead) -> dict:
    when = (lead.created_at or datetime.now(timezone.utc)).strftime("%d/%m/%Y %H:%M UTC")
    return {
        "nome": lead.name,
        "azienda": lead.company,
        "email": lead.email,
        "telefono": lead.phone,
        "note": lead.note,
        "conversazione": lead.conversation,
        "consenso": f"Sì, il {when}: «{lead.consent_text}»",
    }


# ============ Schemas ============

class ConsentRequest(BaseModel):
    config_id: str = Field(..., max_length=50)
    page: Optional[str] = Field(None, max_length=1000)


class LeadFields(BaseModel):
    nome: str = Field("", max_length=200)
    email: str = Field("", max_length=320)
    telefono: Optional[str] = Field(None, max_length=60)
    azienda: Optional[str] = Field(None, max_length=300)
    note: Optional[str] = Field(None, max_length=3000)
    consenso: bool = False
    website: Optional[str] = Field(None, max_length=200)  # honeypot: real visitors leave it empty


class LeadSubmission(BaseModel):
    config_id: str = Field(..., max_length=50)
    consent_id: Optional[str] = Field(None, max_length=36)
    fields: LeadFields
    conversation: List[str] = Field(default_factory=list, max_length=40)
    page: Optional[str] = Field(None, max_length=1000)


class TestLeadRequest(BaseModel):
    lead_emails: str = Field(..., max_length=1000)
    bot_name: Optional[str] = Field(None, max_length=255)
    fields: Optional[LeadFields] = None  # the preview's form; sample data if missing
    conversation: List[str] = Field(default_factory=list, max_length=40)


def clean_lead(fields: LeadFields) -> dict:
    """Validated lead values, or a 422 with a message the visitor can act on."""
    name = _single_line(fields.nome, 120)
    email = _single_line(fields.email, 320)
    phone = _single_line(fields.telefono, 40)
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Inserisci nome e cognome.")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="L'indirizzo email non sembra valido.")
    if phone and not PHONE_RE.match(phone):
        raise HTTPException(status_code=422, detail="Il numero di telefono non sembra valido.")
    if not fields.consenso:
        raise HTTPException(status_code=422, detail="Per inviare la richiesta serve il consenso al trattamento dei dati.")
    return {
        "name": name,
        "email": email,
        "phone": phone or None,
        "company": _single_line(fields.azienda, 200) or None,
        "note": (fields.note or "").strip()[:2000] or None,
    }


def conversation_excerpt(messages: List[str]) -> Optional[str]:
    """The visitor's last messages, for the team that calls back."""
    parts = [m.strip()[:600] for m in messages[-12:] if isinstance(m, str) and m.strip()]
    text = "\n".join(f"• {p}" for p in parts)
    return text[:4000] or None


# ============ Public endpoints (widget) ============

@router.post("/api/widget/consent")
async def widget_consent(body: ConsentRequest, req: Request, db: Session = Depends(get_db)):
    """Record that a visitor accepted the bot's privacy notice."""
    config = db.query(ClippyConfig).filter(ClippyConfig.config_id == body.config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration not found")
    if not origin_allowed(config, req):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Domain not allowed")
    if not config.privacy_enabled:
        return {"consent_id": None, "required": False}
    if not _limits.allow(f"consent:{get_client_ip(req)}", 30, 600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Troppe richieste, riprova tra poco.")
    event = ConsentEvent(
        id=str(uuid.uuid4()),
        config_id=config.id,
        text_version=privacy_settings(config)["version"],
        page_url=_page_url(body.page),
    )
    db.add(event)
    db.commit()
    return {"consent_id": event.id, "version": event.text_version}


@router.post("/api/widget/lead")
async def widget_lead(body: LeadSubmission, req: Request, db: Session = Depends(get_db)):
    """A visitor sent the lead form: store it, then email it to the bot's recipients."""
    ip = get_client_ip(req)
    if not _limits.allow(f"lead:{ip}", 5, 600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Hai già inviato diverse richieste: riprova più tardi.")
    config = db.query(ClippyConfig).filter(ClippyConfig.config_id == body.config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration not found")
    if not origin_allowed(config, req):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Domain not allowed")
    if not leads_on(config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Il modulo contatti non è attivo per questo assistente.")
    if config.privacy_enabled and not consent_valid(db, config, body.consent_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="consent_required")
    if body.fields.website:
        return {"ok": True}  # honeypot: look successful, store nothing
    if not _limits.allow(f"lead-bot:{config.id}", 30, 3600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Troppe richieste in poco tempo: riprova più tardi.")

    values = clean_lead(body.fields)
    lead = Lead(
        config_id=config.id,
        conversation=conversation_excerpt(body.conversation),
        page_url=_page_url(body.page),
        consent_text=lead_consent_text(config),
        privacy_consent_id=body.consent_id if config.privacy_enabled else None,
        **values,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    delivery, error = await deliver_lead(
        fields=_email_fields(lead),
        recipients=_recipients(config.lead_emails),
        bot_name=_bot_name(config),
        page_url=lead.page_url,
    )
    lead.delivery_status = delivery
    lead.delivery_error = error
    if delivery == "sent":
        lead.delivered_at = datetime.now(timezone.utc)
    db.commit()
    if error:
        print(f"⚠️ lead {lead.id} ({config.config_id}): {delivery} — {error}")
    # The lead is stored either way; a failed email shows up in the dashboard.
    return {"ok": True}


# ============ Owner endpoints (dashboard) ============

@router.get("/api/privacy/defaults")
async def privacy_defaults(current_user: User = Depends(get_current_active_user)):
    return {
        "privacy_text": DEFAULT_PRIVACY_TEXT,
        "privacy_button_label": DEFAULT_PRIVACY_BUTTON,
        "lead_consent_text": DEFAULT_LEAD_CONSENT,
        "relay_configured": bool(FORM_RELAY_TOKEN),
    }


@router.post("/api/leads/test")
async def send_test_lead(body: TestLeadRequest, current_user: User = Depends(get_current_active_user)):
    """Send a "[PROVA]" lead to the given recipients: sample data, or the
    preview's form. Nothing is stored."""
    try:
        recipients = _recipients(normalise_lead_emails(body.lead_emails))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not recipients:
        raise HTTPException(status_code=422, detail="Inserisci almeno un indirizzo email.")
    if not _limits.allow(f"test:{current_user.id}", 10, 600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Troppe prove in poco tempo: riprova tra qualche minuto.")
    sample = body.fields or LeadFields(
        nome="Mario Rossi (prova)", email="mario.rossi@example.com", telefono="+39 333 1234567",
        azienda="Rossi Meccanica Srl", note="Email di prova inviata dalla dashboard di Clippy.", consenso=True,
    )
    values = clean_lead(sample)
    fields = {
        "nome": values["name"], "azienda": values["company"], "email": values["email"],
        "telefono": values["phone"], "note": values["note"],
        "conversazione": conversation_excerpt(body.conversation),
        "consenso": "Sì (prova dalla dashboard)",
    }
    delivery, error = await deliver_lead(
        fields=fields, recipients=recipients, bot_name=_bot_name(body.bot_name or ""), page_url=None, test=True,
    )
    return {"ok": delivery == "sent", "status": delivery, "error": error, "recipients": recipients}


def _owned_config(db: Session, config_id: str, user: User) -> ClippyConfig:
    config = db.query(ClippyConfig).filter(ClippyConfig.config_id == config_id, ClippyConfig.user_id == user.id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration not found")
    return config


def _owned_lead(db: Session, lead_id: int, user: User) -> Lead:
    lead = (
        db.query(Lead).join(ClippyConfig, Lead.config_id == ClippyConfig.id)
        .filter(Lead.id == lead_id, ClippyConfig.user_id == user.id).first()
    )
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


def _lead_out(lead: Lead, retention_days: Optional[int] = None) -> dict:
    expires = lead.created_at + timedelta(days=retention_days) if lead.created_at and retention_days else None
    return {
        "id": lead.id,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "expires_at": expires.isoformat() if expires else None,
        "name": lead.name, "email": lead.email, "phone": lead.phone, "company": lead.company,
        "note": lead.note, "conversation": lead.conversation, "page_url": lead.page_url,
        "consent_text": lead.consent_text,
        "delivery_status": lead.delivery_status, "delivery_error": lead.delivery_error,
    }


@router.get("/api/configs/{config_id}/leads")
async def list_leads(config_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    config = _owned_config(db, config_id, current_user)
    leads = db.query(Lead).filter(Lead.config_id == config.id).order_by(Lead.id.desc()).limit(500).all()
    days = config.data_retention_days or DEFAULT_RETENTION_DAYS
    return {"leads": [_lead_out(lead, days) for lead in leads], "retention_days": days}


@router.delete("/api/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(lead_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.delete(_owned_lead(db, lead_id, current_user))
    db.commit()
    return None


@router.post("/api/leads/{lead_id}/resend")
async def resend_lead(lead_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lead = _owned_lead(db, lead_id, current_user)
    config = db.query(ClippyConfig).filter(ClippyConfig.id == lead.config_id).first()
    delivery, error = await deliver_lead(
        fields=_email_fields(lead), recipients=_recipients(config.lead_emails),
        bot_name=_bot_name(config), page_url=lead.page_url,
    )
    lead.delivery_status = delivery
    lead.delivery_error = error
    if delivery == "sent":
        lead.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return _lead_out(lead, config.data_retention_days or DEFAULT_RETENTION_DAYS)


def delete_bot_data(db: Session, config: ClippyConfig) -> None:
    """Leads and consent records go with the bot that collected them."""
    db.query(Lead).filter(Lead.config_id == config.id).delete()
    db.query(ConsentEvent).filter(ConsentEvent.config_id == config.id).delete()


# ============ Automatic deletion (retention) ============

def purge_expired(db: Session, now: Optional[datetime] = None) -> dict:
    """Delete leads and consent records older than each bot's retention period."""
    now = now or datetime.now(timezone.utc)
    removed = {"leads": 0, "consents": 0}
    for config in db.query(ClippyConfig).all():
        days = config.data_retention_days or DEFAULT_RETENTION_DAYS
        cutoff = (now - timedelta(days=days)).replace(tzinfo=None)  # stored as naive UTC
        removed["leads"] += (
            db.query(Lead).filter(Lead.config_id == config.id, Lead.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        removed["consents"] += (
            db.query(ConsentEvent).filter(ConsentEvent.config_id == config.id, ConsentEvent.created_at < cutoff)
            .delete(synchronize_session=False)
        )
    db.commit()
    return removed


async def _retention_loop():
    while True:
        try:
            db = SessionLocal()
            try:
                removed = purge_expired(db)
            finally:
                db.close()
            if removed["leads"] or removed["consents"]:
                print(f"🗑️ Retention: deleted {removed['leads']} lead(s) and {removed['consents']} consent record(s)")
        except Exception as e:  # a failed sweep must not stop the next ones
            print(f"⚠️ Retention sweep failed: {e}")
        await asyncio.sleep(RETENTION_SWEEP_SECONDS)


_sweeper = None


def start_retention_sweeps() -> None:
    """Run the deletion sweep now and every RETENTION_SWEEP_SECONDS (from the app's startup)."""
    global _sweeper
    if _sweeper is None or _sweeper.done():
        _sweeper = asyncio.get_running_loop().create_task(_retention_loop())
