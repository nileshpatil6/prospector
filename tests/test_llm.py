import pytest

from prospector.llm import GeminiLLM, LLMError, _extract_retry_delay


def _make_llm() -> GeminiLLM:
    # Constructing genai.Client(api_key=...) does not touch the network --
    # it just stores config -- so this is safe offline. Every test below
    # monkeypatches _generate so no real API call is ever made.
    return GeminiLLM(api_key="fake-key-for-tests", model="fake-model")


# --- HIGH: a non-dict JSON response is a parse failure, not a silent pass ---

def test_json_raises_llm_error_when_response_is_a_list_both_tries(monkeypatch):
    llm = _make_llm()
    calls = {"n": 0}

    def fake_generate(system, user, *, json_mode):
        calls["n"] += 1
        return "[1, 2, 3]"  # syntactically valid JSON, but not an object

    monkeypatch.setattr(llm, "_generate", fake_generate)

    with pytest.raises(LLMError):
        llm.json("sys", "user", "hint")
    assert calls["n"] == 2  # original attempt + one retry, then give up


def test_json_succeeds_on_retry_after_a_non_dict_first_response(monkeypatch):
    llm = _make_llm()
    responses = iter(['"just a string"', '{"ok": true}'])

    monkeypatch.setattr(llm, "_generate", lambda system, user, *, json_mode: next(responses))

    result = llm.json("sys", "user", "hint")
    assert result == {"ok": True}


def test_json_returns_dict_on_first_valid_response(monkeypatch):
    llm = _make_llm()
    monkeypatch.setattr(llm, "_generate", lambda system, user, *, json_mode: '{"a": 1}')
    assert llm.json("sys", "user", "hint") == {"a": 1}


def test_json_strips_code_fences_before_checking_object_shape(monkeypatch):
    llm = _make_llm()
    monkeypatch.setattr(llm, "_generate", lambda system, user, *, json_mode: '```json\n{"a": 1}\n```')
    assert llm.json("sys", "user", "hint") == {"a": 1}


# --- MED: retry-delay extraction for 429 backoff ---------------------------

def test_extract_retry_delay_parses_string_form():
    exc = RuntimeError('429 rate limited, RetryInfo: {"retryDelay": "45s"}')
    assert _extract_retry_delay(exc) == 45.0


def test_extract_retry_delay_none_when_absent():
    assert _extract_retry_delay(RuntimeError("plain old error")) is None


def test_extract_retry_delay_reads_numeric_attribute():
    class FakeExc(Exception):
        retry_delay = 12.5

    assert _extract_retry_delay(FakeExc()) == 12.5
