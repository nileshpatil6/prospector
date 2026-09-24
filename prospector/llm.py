"""LLM abstraction: a tiny Protocol plus a Gemini-backed implementation and a
scripted stand-in for offline tests.

Every call site in this project goes through `LLM.json` or `LLM.text` so the
whole agent can run against `ScriptedLLM` with zero network access.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Raised when the LLM layer cannot produce a usable response."""


@runtime_checkable
class LLM(Protocol):
    def json(self, system: str, user: str, schema_hint: str) -> dict: ...

    def text(self, system: str, user: str) -> str: ...


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_fences(raw: str) -> str:
    """Gemini's JSON mode can still wrap output in ``` fences on retries."""
    return _FENCE_RE.sub("", raw.strip()).strip()


class GeminiLLM:
    """LLM backed by Google's Gemini API via the `google-genai` SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

        from google import genai  # imported lazily so offline paths never need it

        self._client = genai.Client(api_key=api_key)

    def _generate(self, system: str, user: str, *, json_mode: bool) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json" if json_mode else "text/plain",
        )

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=config,
                )
                return response.text or ""
            except Exception as exc:  # noqa: BLE001 - broad: retry transient errors
                last_error = exc
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                transient = status in (429, 500, 502, 503, 504) or status is None
                if not transient or attempt == 2:
                    raise LLMError(f"Gemini call failed: {exc}") from exc
                time.sleep(2**attempt)
        raise LLMError(f"Gemini call failed: {last_error}")

    def json(self, system: str, user: str, schema_hint: str) -> dict:
        full_user = f"{user}\n\nRespond with JSON matching this shape:\n{schema_hint}"
        raw = self._generate(system, full_user, json_mode=True)
        try:
            return json.loads(_strip_fences(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            # One retry with the parse error appended, as the contract specifies.
            retry_user = (
                f"{full_user}\n\nYour previous response failed to parse as JSON "
                f"({exc}). Previous response was:\n{raw}\n\nReturn ONLY valid JSON."
            )
            raw2 = self._generate(system, retry_user, json_mode=True)
            try:
                return json.loads(_strip_fences(raw2))
            except (json.JSONDecodeError, TypeError) as exc2:
                raise LLMError(f"Gemini did not return valid JSON: {exc2}") from exc2

    def text(self, system: str, user: str) -> str:
        return self._generate(system, user, json_mode=False)


class ScriptedLLM:
    """Deterministic LLM stand-in for tests: pops queued responses in order.

    `responses` is a list of either dicts (returned by `json`) or strings
    (returned by `text`). Each call pops the next entry, regardless of which
    method is invoked, mirroring the order the real agent would call the LLM.
    Every call is recorded in `.calls` as (method, system, user) so tests can
    assert on what the agent actually sent (e.g. the holdout-isolation check).
    """

    def __init__(self, responses: list[dict | str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, str]] = []

    def json(self, system: str, user: str, schema_hint: str) -> dict:
        self.calls.append(("json", system, user))
        if not self._responses:
            raise LLMError("ScriptedLLM has no more queued responses")
        response = self._responses.pop(0)
        if not isinstance(response, dict):
            raise LLMError(f"ScriptedLLM expected a dict response, got {response!r}")
        return response

    def text(self, system: str, user: str) -> str:
        self.calls.append(("text", system, user))
        if not self._responses:
            raise LLMError("ScriptedLLM has no more queued responses")
        response = self._responses.pop(0)
        if not isinstance(response, str):
            raise LLMError(f"ScriptedLLM expected a str response, got {response!r}")
        return response
