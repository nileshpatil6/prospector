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


# Free-tier 429s ask for a 30-60s cooldown, not the 1s/2s a naive exponential
# backoff would give. These are the fallback delays when the API doesn't
# tell us how long to wait.
RETRY_DELAYS_S = (15.0, 30.0, 45.0)
MAX_ATTEMPTS = 4

_RETRY_DELAY_RE = re.compile(r"retrydelay[\"']?\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)\s*s?", re.IGNORECASE)


def _extract_retry_delay(exc: Exception) -> float | None:
    """Best-effort extraction of a server-suggested retry delay (google.rpc.
    RetryInfo) from an SDK exception. Checks common attribute names first,
    then falls back to regex-scanning the exception's string form, since the
    exact shape varies across google-genai SDK versions."""
    for attr in ("retry_delay", "retryDelay"):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        seconds = getattr(value, "seconds", None)
        if isinstance(seconds, (int, float)):
            return float(seconds)
    match = _RETRY_DELAY_RE.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


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
        for attempt in range(MAX_ATTEMPTS):
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
                if not transient or attempt == MAX_ATTEMPTS - 1:
                    raise LLMError(f"Gemini call failed: {exc}") from exc
                delay = _extract_retry_delay(exc)
                if delay is None:
                    delay = RETRY_DELAYS_S[min(attempt, len(RETRY_DELAYS_S) - 1)]
                time.sleep(delay)
        raise LLMError(f"Gemini call failed: {last_error}")

    @staticmethod
    def _parse_json_object(raw: str) -> dict | None:
        """Parse `raw` as JSON and return it only if it's an object. A
        syntactically valid JSON array/string/number is still a parse
        FAILURE for our purposes -- every call site expects a dict."""
        try:
            value = json.loads(_strip_fences(raw))
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def json(self, system: str, user: str, schema_hint: str) -> dict:
        full_user = f"{user}\n\nRespond with a JSON OBJECT matching this shape:\n{schema_hint}"
        raw = self._generate(system, full_user, json_mode=True)
        parsed = self._parse_json_object(raw)
        if parsed is not None:
            return parsed

        # One retry with the parse error appended, as the contract specifies.
        retry_user = (
            f"{full_user}\n\nYour previous response failed to parse as a JSON object "
            f"(it must be a top-level object, not an array or scalar). Previous "
            f"response was:\n{raw}\n\nReturn ONLY a valid JSON object."
        )
        raw2 = self._generate(system, retry_user, json_mode=True)
        parsed2 = self._parse_json_object(raw2)
        if parsed2 is not None:
            return parsed2
        raise LLMError("Gemini did not return a valid JSON object after one retry")

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
