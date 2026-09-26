"""Tests for prospector/live.py. Never touches the real Gemini API -- every
test injects a fake client into create_live_session().
"""

from __future__ import annotations

from prospector.live import (
    LIVE_MODEL,
    LiveSessionError,
    build_live_config,
    create_live_session,
)
from prospector.osm import Lead
from prospector.receptionist import default_receptionist_prompt


class _FakeToken:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeAuthTokens:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, config: dict) -> _FakeToken:
        self.calls.append(config)
        return _FakeToken("fake-ephemeral-token")


class _FakeClient:
    def __init__(self) -> None:
        self.auth_tokens = _FakeAuthTokens()


def _fake_lead() -> Lead:
    return Lead(
        id="osm:node/1", name="Sunrise Dental Care", niche="dentist",
        lat=18.52, lon=73.85, address="FC Road, Pune", opening_hours="Mo-Sa 09:00-19:00",
    )


def test_build_live_config_has_locked_shape():
    config = build_live_config("You are the AI receptionist of Sunrise Dental Care.")
    assert config["response_modalities"] == ["AUDIO"]
    assert config["system_instruction"] == "You are the AI receptionist of Sunrise Dental Care."
    assert config["input_audio_transcription"] == {}
    assert config["output_audio_transcription"] == {}
    assert config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Kore"
    declarations = config["tools"][0]["function_declarations"]
    assert declarations[0]["name"] == "take_message"
    assert set(declarations[0]["parameters"]["required"]) == {
        "caller_name", "callback_number", "reason",
    }


def test_create_live_session_uses_leads_own_prompt():
    lead = _fake_lead()
    lead.receptionist_prompt = "You are the AI receptionist of Sunrise Dental Care. Custom persona."
    client = _FakeClient()

    session = create_live_session(lead, client=client)

    assert session["token"] == "fake-ephemeral-token"
    assert session["model"] == LIVE_MODEL
    assert session["config"]["system_instruction"] == lead.receptionist_prompt


def test_create_live_session_falls_back_to_default_prompt_when_empty():
    lead = _fake_lead()
    assert lead.receptionist_prompt == ""
    client = _FakeClient()

    session = create_live_session(lead, client=client)

    assert session["config"]["system_instruction"] == default_receptionist_prompt(lead)


def test_create_live_session_locks_the_token_to_model_and_config():
    lead = _fake_lead()
    client = _FakeClient()

    session = create_live_session(lead, client=client, model="gemini-3.8-live")

    assert len(client.auth_tokens.calls) == 1
    call = client.auth_tokens.calls[0]
    assert call["uses"] == 1
    constraints = call["live_connect_constraints"]
    assert constraints["model"] == "gemini-3.8-live"
    assert constraints["config"] == session["config"]


def test_create_live_session_without_key_or_client_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    lead = _fake_lead()

    try:
        create_live_session(lead)
        assert False, "expected LiveSessionError"
    except LiveSessionError as exc:
        assert "GEMINI_API_KEY" in str(exc)
