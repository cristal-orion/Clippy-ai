"""
Interactive UI (OpenUI) for modern-mode bots.

The widget renders replies written in OpenUI Lang with static/clippy-ui.js. The
system-prompt sections that teach the model that language are generated from
the same component library (ui/, `npm run build` or the Node stage of the
Dockerfile). Without the prompt files the option is ignored and replies stay
plain text.
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_prompt(name: str) -> str:
    try:
        with open(os.path.join(_HERE, name), encoding="utf-8") as f:
            return "\n\n" + f.read().strip()
    except OSError:
        return ""


# Base components; the second variant adds the lead form (LeadForm)
OPENUI_PROMPT = _load_prompt("openui_prompt.txt")
OPENUI_LEADS_PROMPT = _load_prompt("openui_prompt_leads.txt")


def generative_ui_on(config) -> bool:
    """Interactive UI applies to modern-mode bots that opted in, when it's built."""
    return bool(OPENUI_PROMPT) and bool(config.generative_ui) and (config.ui_mode or "classic") == "modern"


def leads_on(config) -> bool:
    """The lead form is offered by interactive-UI bots that have lead recipients."""
    return generative_ui_on(config) and bool(OPENUI_LEADS_PROMPT) and bool((config.lead_emails or "").strip())


def openui_prompt(lead_form: bool) -> str:
    return OPENUI_LEADS_PROMPT if lead_form and OPENUI_LEADS_PROMPT else OPENUI_PROMPT
