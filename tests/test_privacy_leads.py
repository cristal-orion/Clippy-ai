"""
Privacy notice, consent records and leads, end to end through the API.

Runs inside the built image (it needs the generated OpenUI prompts):

    docker run --rm -v "$PWD/tests:/app/tests:ro" -w /app \
        -e DATABASE_URL=sqlite:////tmp/clippy-test.db <image> \
        python -m unittest tests.test_privacy_leads -v

The model and form-relay are faked: nothing leaves the container.
"""

import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/clippy-test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ["FORM_RELAY_TOKEN"] = "relay-test-token"

if os.environ["DATABASE_URL"].startswith("sqlite:////tmp/") and os.path.exists(os.environ["DATABASE_URL"][10:]):
    os.remove(os.environ["DATABASE_URL"][10:])

from fastapi.testclient import TestClient  # noqa: E402

import leads  # noqa: E402
import main  # noqa: E402

sent = []  # payloads that would have gone to form-relay
relay_status = {"code": 200}
model_calls = []


class FakeRelayResponse:
    def __init__(self, code):
        self.status_code = code

    def json(self):
        return {"ok": self.status_code == 200, "message": "finto"}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        sent.append({"url": url, "json": json, "headers": headers})
        return FakeRelayResponse(relay_status["code"])


class FakeUsage(dict):
    pass


class FakeModelResponse:
    usage = FakeUsage(prompt_tokens=1, completion_tokens=1)


async def fake_completion(model_name, messages, **kwargs):
    model_calls.append(messages)
    return 'root = Col([Text("ciao")])', FakeModelResponse()


leads.httpx.AsyncClient = FakeAsyncClient
main.complete_with_continuation = fake_completion


class _Ctx:
    """Client, users and the main test bot, shared by every test class."""


ctx = _Ctx()


def register(email, username):
    res = ctx.client.post("/api/auth/register", json={"email": email, "username": username, "password": "password123"})
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def setUpModule():
    ctx.client = TestClient(main.app)
    ctx.client.__enter__()  # runs the startup hook: creates the tables
    ctx.token = register("owner@example.com", "owner")
    ctx.other = register("other@example.com", "other")
    res = ctx.client.post("/api/configs", headers={"Authorization": f"Bearer {ctx.token}"}, json={
        "name": "Icura Bot", "provider": "gemini", "model": "gemini-x", "api_key": "k",
        "system_prompt": "Istruzioni riservate", "ui_mode": "modern", "generative_ui": True,
        "privacy_enabled": True, "privacy_policy_url": "https://cliente.example/privacy",
        "lead_emails": "commerciale@cliente.example; titolare@cliente.example",
    })
    assert res.status_code == 201, res.text
    ctx.config_id = res.json()["config_id"]


def tearDownModule():
    ctx.client.__exit__(None, None, None)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.token, cls.other, cls.config_id = ctx.client, ctx.token, ctx.other, ctx.config_id

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def setUp(self):
        sent.clear()
        model_calls.clear()
        relay_status["code"] = 200
        leads._limits.hits.clear()


class PrivacyAndLeads(ApiTest):
    def consent(self):
        res = self.client.post("/api/widget/consent", json={"config_id": self.config_id, "page": "https://cliente.example/"})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["consent_id"]

    def chat(self, consent_id=None):
        return self.client.post("/api/widget/chat", json={
            "config_id": self.config_id, "consent_id": consent_id,
            "messages": [{"role": "user", "content": "Ciao"}],
        })

    def lead(self, consent_id, **fields):
        body = {"nome": "Mario Rossi", "email": "mario@rossi.example", "telefono": "+39 333 1234567",
                "azienda": "Rossi Srl", "note": "Macchinari per 300k", "consenso": True}
        body.update(fields)
        return self.client.post("/api/widget/lead", json={
            "config_id": self.config_id, "consent_id": consent_id, "fields": body,
            "conversation": ["Ho un'azienda in Lombardia", "Vorrei una consulenza"],
            "page": "https://cliente.example/bandi",
        })

    def list_leads(self, token=None):
        return self.client.get(f"/api/configs/{self.config_id}/leads", headers=self.auth(token or self.token))

    # ---- widget config ----

    def test_widget_config_exposes_privacy_and_leads_but_not_secrets(self):
        cfg = self.client.get(f"/api/widget/config/{self.config_id}").json()["config"]
        self.assertNotIn("system_prompt", cfg)
        self.assertNotIn("lead_emails", cfg)
        self.assertTrue(cfg["privacy"]["enabled"])
        self.assertEqual(cfg["privacy"]["policy_url"], "https://cliente.example/privacy")
        self.assertEqual(cfg["privacy"]["text"], leads.DEFAULT_PRIVACY_TEXT)
        self.assertEqual(len(cfg["privacy"]["version"]), 16)
        self.assertTrue(cfg["leads"]["enabled"])
        self.assertEqual(cfg["leads"]["consent_text"], leads.DEFAULT_LEAD_CONSENT)

    def test_owner_sees_normalised_lead_emails(self):
        cfg = self.client.get(f"/api/configs/{self.config_id}", headers=self.auth(self.token)).json()
        self.assertEqual(cfg["lead_emails"], "commerciale@cliente.example, titolare@cliente.example")

    # ---- consent ----

    def test_chat_requires_consent(self):
        self.assertEqual(self.chat().status_code, 403)
        self.assertEqual(self.chat().json()["detail"], "consent_required")
        self.assertEqual(self.chat("not-a-real-id").status_code, 403)
        self.assertEqual(model_calls, [], "no model call before consent")

    def test_chat_with_consent_uses_the_lead_form_prompt(self):
        res = self.chat(self.consent())
        self.assertEqual(res.status_code, 200, res.text)
        system = model_calls[0][0]["content"]
        self.assertIn("LeadForm", system)
        self.assertIn("Istruzioni riservate", system)

    def test_changing_the_notice_asks_for_consent_again(self):
        consent_id = self.consent()
        self.assertEqual(self.chat(consent_id).status_code, 200)
        self.client.put(f"/api/configs/{self.config_id}", headers=self.auth(self.token), json={"privacy_text": "Nuovo testo"})
        try:
            self.assertEqual(self.chat(consent_id).status_code, 403)
            self.assertEqual(self.chat(self.consent()).status_code, 200)
        finally:
            self.client.put(f"/api/configs/{self.config_id}", headers=self.auth(self.token), json={"privacy_text": ""})

    # ---- leads ----

    def test_lead_is_stored_and_sent_through_form_relay(self):
        res = self.lead(self.consent())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(len(sent), 1)
        call = sent[0]
        self.assertTrue(call["url"].endswith("/s/clippy"))
        self.assertEqual(call["headers"]["Authorization"], "Bearer relay-test-token")
        payload = call["json"]
        self.assertEqual(payload["to"], [{"email": "commerciale@cliente.example"}, {"email": "titolare@cliente.example"}])
        self.assertEqual(payload["sourceLabel"], "Icura Bot")
        self.assertIn("{{nome}}", payload["subject"])
        self.assertEqual(payload["fields"]["email"], "mario@rossi.example")
        self.assertIn("Vorrei una consulenza", payload["fields"]["conversazione"])
        self.assertIn(leads.DEFAULT_LEAD_CONSENT, payload["fields"]["consenso"])
        self.assertEqual(payload["meta"]["page"], "https://cliente.example/bandi")

        stored = self.list_leads().json()["leads"][0]
        self.assertEqual(stored["delivery_status"], "sent")
        self.assertEqual(stored["consent_text"], leads.DEFAULT_LEAD_CONSENT)

    def test_lead_needs_consent_and_valid_data(self):
        self.assertEqual(self.lead(None).status_code, 403)
        consent_id = self.consent()
        self.assertEqual(self.lead(consent_id, email="non-una-mail").status_code, 422)
        self.assertEqual(self.lead(consent_id, consenso=False).status_code, 422)
        self.assertEqual(self.lead(consent_id, nome="").status_code, 422)
        self.assertEqual(self.lead(consent_id, telefono="chiamami <b>").status_code, 422)
        self.assertEqual(sent, [])

    def test_honeypot_looks_successful_but_stores_nothing(self):
        before = len(self.list_leads().json()["leads"])
        res = self.lead(self.consent(), website="http://spam.example")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(sent, [])
        self.assertEqual(len(self.list_leads().json()["leads"]), before)

    def test_failed_delivery_keeps_the_lead_and_can_be_resent(self):
        relay_status["code"] = 500
        self.assertEqual(self.lead(self.consent()).status_code, 200)
        stored = self.list_leads().json()["leads"][0]
        self.assertEqual(stored["delivery_status"], "failed")
        relay_status["code"] = 200
        res = self.client.post(f"/api/leads/{stored['id']}/resend", headers=self.auth(self.token))
        self.assertEqual(res.json()["delivery_status"], "sent")

    def test_lead_rate_limit_per_visitor(self):
        consent_id = self.consent()
        codes = [self.lead(consent_id).status_code for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_leads_belong_to_their_owner(self):
        self.lead(self.consent())
        self.assertEqual(self.list_leads(self.other).status_code, 404)
        lead_id = self.list_leads().json()["leads"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/leads/{lead_id}", headers=self.auth(self.other)).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/leads/{lead_id}", headers=self.auth(self.token)).status_code, 204)

    def test_test_email_is_marked_and_not_stored(self):
        before = len(self.list_leads().json()["leads"])
        res = self.client.post("/api/leads/test", headers=self.auth(self.token),
                               json={"lead_emails": "prova@cliente.example", "bot_name": "Icura Bot"})
        self.assertTrue(res.json()["ok"], res.text)
        self.assertTrue(sent[0]["json"]["subject"].startswith("[PROVA]"))
        self.assertEqual(sent[0]["json"]["to"], [{"email": "prova@cliente.example"}])
        self.assertEqual(len(self.list_leads().json()["leads"]), before)
        bad = self.client.post("/api/leads/test", headers=self.auth(self.token), json={"lead_emails": "x"})
        self.assertEqual(bad.status_code, 422)

    def test_lead_form_off_without_recipients(self):
        res = self.client.post("/api/configs", headers=self.auth(self.token), json={
            "name": "Senza contatti", "provider": "gemini", "model": "m", "api_key": "k",
            "ui_mode": "modern", "generative_ui": True,
        })
        config_id = res.json()["config_id"]
        cfg = self.client.get(f"/api/widget/config/{config_id}").json()["config"]
        self.assertFalse(cfg["leads"]["enabled"])
        self.assertFalse(cfg["privacy"]["enabled"])
        res = self.client.post("/api/widget/lead", json={"config_id": config_id, "fields": {"nome": "A B", "email": "a@b.example", "consenso": True}})
        self.assertEqual(res.status_code, 403)

    def test_deleting_a_bot_deletes_its_leads_and_consents(self):
        res = self.client.post("/api/configs", headers=self.auth(self.token), json={
            "name": "Da cancellare", "provider": "gemini", "model": "m", "api_key": "k",
            "ui_mode": "modern", "generative_ui": True, "privacy_enabled": True, "lead_emails": "a@b.example",
        })
        config_id = res.json()["config_id"]
        consent = self.client.post("/api/widget/consent", json={"config_id": config_id}).json()["consent_id"]
        self.client.post("/api/widget/lead", json={"config_id": config_id, "consent_id": consent,
                                                   "fields": {"nome": "A B", "email": "a@b.example", "consenso": True}})
        self.assertEqual(self.client.delete(f"/api/configs/{config_id}", headers=self.auth(self.token)).status_code, 204)
        from database import SessionLocal
        from models import ConsentEvent, Lead
        db = SessionLocal()
        try:
            self.assertEqual(db.query(ConsentEvent).filter(ConsentEvent.id == consent).count(), 0)
            self.assertEqual(db.query(Lead).filter(Lead.email == "a@b.example").count(), 0)
        finally:
            db.close()


class Retention(ApiTest):
    """Leads and consent records are deleted after each bot's retention period."""

    def make_bot(self, **extra):
        res = self.client.post("/api/configs", headers=self.auth(self.token), json={
            "name": "Ritenzione", "provider": "gemini", "model": "m", "api_key": "k", "ui_mode": "modern",
            "generative_ui": True, "privacy_enabled": True, "lead_emails": "a@b.example", **extra,
        })
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def age(self, model, config_pk, days):
        from datetime import datetime, timedelta
        from database import SessionLocal
        db = SessionLocal()
        try:
            for row in db.query(model).filter(model.config_id == config_pk).all():
                row.created_at = datetime.utcnow() - timedelta(days=days)
            db.commit()
        finally:
            db.close()

    def collect(self, config_id):
        consent = self.client.post("/api/widget/consent", json={"config_id": config_id}).json()["consent_id"]
        res = self.client.post("/api/widget/lead", json={"config_id": config_id, "consent_id": consent,
                                                         "fields": {"nome": "A B", "email": "a@b.example", "consenso": True}})
        self.assertEqual(res.status_code, 200, res.text)

    def counts(self, config_pk):
        from database import SessionLocal
        from models import ConsentEvent, Lead
        db = SessionLocal()
        try:
            return (db.query(Lead).filter(Lead.config_id == config_pk).count(),
                    db.query(ConsentEvent).filter(ConsentEvent.config_id == config_pk).count())
        finally:
            db.close()

    def purge(self):
        from database import SessionLocal
        db = SessionLocal()
        try:
            return leads.purge_expired(db)
        finally:
            db.close()

    def test_default_is_90_days(self):
        self.assertEqual(self.make_bot()["data_retention_days"], 90)

    def test_expired_data_is_deleted_and_recent_data_kept(self):
        from models import ConsentEvent, Lead
        bot = self.make_bot()
        self.collect(bot["config_id"])
        self.age(Lead, bot["id"], 89)
        self.age(ConsentEvent, bot["id"], 89)
        self.purge()
        self.assertEqual(self.counts(bot["id"]), (1, 1), "89 days: still within 3 months")
        self.age(Lead, bot["id"], 91)
        self.age(ConsentEvent, bot["id"], 91)
        self.purge()
        self.assertEqual(self.counts(bot["id"]), (0, 0), "91 days: deleted")

    def test_each_bot_keeps_its_own_period(self):
        from models import Lead
        short = self.make_bot(data_retention_days=7)
        long = self.make_bot(data_retention_days=365)
        for bot in (short, long):
            self.collect(bot["config_id"])
            self.age(Lead, bot["id"], 30)
        self.purge()
        self.assertEqual(self.counts(short["id"])[0], 0)
        self.assertEqual(self.counts(long["id"])[0], 1)

    def test_lead_list_shows_the_deletion_date(self):
        bot = self.make_bot(data_retention_days=30)
        self.collect(bot["config_id"])
        data = self.client.get(f"/api/configs/{bot['config_id']}/leads", headers=self.auth(self.token)).json()
        self.assertEqual(data["retention_days"], 30)
        self.assertTrue(data["leads"][0]["expires_at"])

    def test_retention_out_of_range_is_rejected(self):
        for days in (0, 3, 1000):
            res = self.client.put(f"/api/configs/{self.config_id}", headers=self.auth(self.token), json={"data_retention_days": days})
            self.assertEqual(res.status_code, 422, days)


class ClientIp(unittest.TestCase):
    def test_forwarded_for_is_used_only_behind_a_private_proxy(self):
        class Req:
            def __init__(self, peer, xff):
                self.client = type("C", (), {"host": peer})()
                self.headers = {"x-forwarded-for": xff} if xff else {}

        self.assertEqual(leads.get_client_ip(Req("10.0.1.4", "93.70.1.2, 10.0.1.4")), "93.70.1.2")
        self.assertEqual(leads.get_client_ip(Req("8.8.8.8", "1.2.3.4")), "8.8.8.8")
        self.assertEqual(leads.get_client_ip(Req("10.0.1.4", None)), "10.0.1.4")


if __name__ == "__main__":
    unittest.main()
