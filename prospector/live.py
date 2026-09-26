"""Gemini Live API session minting for the AI receptionist demo.

The browser never sees the real GEMINI_API_KEY. Instead, the server mints a
short-lived, single-use ephemeral auth token locked (via
`live_connect_constraints`) to one model and one fully-formed Live config --
the browser can connect with it but can't repurpose it for a different model
or a different persona. Verified live against the real API (see the
contract this module implements): `genai.Client(api_key=token.name, ...)`
followed by `aio.live.connect(model, config)` works.
"""

from __future__ import annotations

import datetime
import os
from typing import Any

from prospector.osm import Lead
from prospector.receptionist import default_receptionist_prompt

LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
LIVE_MODEL_FALLBACK = "gemini-2.5-flash-native-audio-latest"

TOKEN_TTL_MINUTES = 30
SESSION_TTL_MINUTES = 2

TAKE_MESSAGE_DECLARATION: dict[str, Any] = {
    "name": "take_message",
    "description": "Record a message for a staff member to call the caller back.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "caller_name": {"type": "STRING", "description": "The caller's name."},
            "callback_number": {"type": "STRING", "description": "A number to call them back on."},
            "reason": {"type": "STRING", "description": "Why they're calling."},
        },
        "required": ["caller_name", "callback_number", "reason"],
    },
}


class LiveSessionError(Exception):
    """Raised when a Live session can't be minted (e.g. no API key)."""


def build_live_config(system_instruction: str) -> dict:
    """The Live connect config, locked into the ephemeral token below. The
    frontend must connect with this exact config -- it's part of the
    token's constraint, not just a suggestion."""
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": system_instruction,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "speech_config": {
            "voice_config": {"prebuilt_voice_config": {"voice_name": "Kore"}}
        },
        "tools": [{"function_declarations": [TAKE_MESSAGE_DECLARATION]}],
    }


def create_live_session(
    lead: Lead,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> dict:
    """Mint a one-use ephemeral token constrained to `model` + this lead's
    persona config. `client` is injectable so tests never touch the real
    Gemini API; when it's omitted, a real `genai.Client` is built from
    GEMINI_API_KEY (raising LiveSessionError if that's unset).
    """
    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LiveSessionError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        from google import genai  # imported lazily so offline paths never need it

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    model = model or LIVE_MODEL
    system_instruction = lead.receptionist_prompt or default_receptionist_prompt(lead)
    config = build_live_config(system_instruction)

    now = datetime.datetime.now(datetime.timezone.utc)
    expire_time = (now + datetime.timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat()
    new_session_expire_time = (now + datetime.timedelta(minutes=SESSION_TTL_MINUTES)).isoformat()

    token = client.auth_tokens.create(
        config={
            "uses": 1,
            "expire_time": expire_time,
            "new_session_expire_time": new_session_expire_time,
            "live_connect_constraints": {"model": model, "config": config},
            "http_options": {"api_version": "v1alpha"},
        }
    )
    return {"token": token.name, "model": model, "config": config}
