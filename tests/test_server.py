"""Tests for the FastAPI server (server.py). No network access, no real LLM
calls -- every test injects a ScriptedLLM (or a small wrapper around one)
via app.state.llm_factory and points runs_dir/data_dir at tmp_path.
"""

from __future__ import annotations

import json
import threading
import time

from fastapi.testclient import TestClient

from prospector.llm import LLMError, ScriptedLLM
from prospector.osm import Lead
from server import create_app


class GatedLLM:
    """Wraps a ScriptedLLM but blocks on the first `.json()` call until the
    test releases it -- used to hold a run "running" long enough to assert
    the 409-on-concurrent-run behavior."""

    def __init__(self, responses: list, started: threading.Event, resume: threading.Event) -> None:
        self._inner = ScriptedLLM(responses)
        self._started = started
        self._resume = resume
        self._first = True

    def json(self, system: str, user: str, schema_hint: str) -> dict:
        if self._first:
            self._first = False
            self._started.set()
            self._resume.wait(timeout=5)
        return self._inner.json(system, user, schema_hint)

    def text(self, system: str, user: str) -> str:
        return self._inner.text(system, user)


def _poll_until_done(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/runs/{run_id}")
        if resp.status_code == 404:
            # background thread hasn't persisted state.json yet
            time.sleep(0.02)
            continue
        data = resp.json()
        if data["status"] != "running":
            return data
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not finish within {timeout}s")


def test_start_run_poll_until_done(tmp_path):
    responses = [
        {"place": "Pune, India", "niches": ["dentist"], "target_count": 1, "plan": ["finish"]},
        {"thought": "nothing to do", "action": "finish", "args": {"summary": "ok"}},
    ]
    app = create_app(
        runs_dir=tmp_path / "runs",
        data_dir=tmp_path / "data",
        llm_factory=lambda: ScriptedLLM(responses),
    )
    client = TestClient(app)

    resp = client.post("/api/runs", json={"goal": "Find dentists"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    assert run_id

    data = _poll_until_done(client, run_id)
    assert data["status"] == "done"
    assert data["goal"] == "Find dentists"
    assert data["final_answer"] == "ok"
    assert data["labels"] == {}

    # list endpoint should include it, newest first.
    listed = client.get("/api/runs").json()
    assert listed[0]["run_id"] == run_id
    assert listed[0]["status"] == "done"

    # report and csv were written by Agent._finalize().
    assert client.get(f"/api/runs/{run_id}/report").status_code == 200
    assert client.get(f"/api/runs/{run_id}/csv").status_code == 200


def test_409_on_concurrent_run(tmp_path):
    started = threading.Event()
    resume = threading.Event()
    responses = [
        {"place": "Pune, India", "niches": ["dentist"], "target_count": 1, "plan": ["finish"]},
        {"thought": "nothing to do", "action": "finish", "args": {"summary": "ok"}},
    ]
    app = create_app(
        runs_dir=tmp_path / "runs",
        data_dir=tmp_path / "data",
        llm_factory=lambda: GatedLLM(responses, started, resume),
    )
    client = TestClient(app)

    resp = client.post("/api/runs", json={"goal": "Find dentists"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    assert started.wait(timeout=5), "background run never started"

    resp2 = client.post("/api/runs", json={"goal": "Find lawyers"})
    assert resp2.status_code == 409
    assert "error" in resp2.json()

    resume.set()
    data = _poll_until_done(client, run_id)
    assert data["status"] == "done"

    # Now that the run is finished, a new run is allowed again. The worker
    # thread clears active_run_id in a `finally` right after agent.run()
    # returns, which can land a beat after state.json reports status="done",
    # so give it a moment.
    deadline = time.monotonic() + 5.0
    resp3 = None
    while time.monotonic() < deadline:
        resp3 = client.post("/api/runs", json={"goal": "Find lawyers"})
        if resp3.status_code == 200:
            break
        time.sleep(0.02)
    assert resp3.status_code == 200


def test_missing_api_key_returns_400_not_500(tmp_path):
    def _raise():
        raise LLMError("GEMINI_API_KEY is not set.")

    app = create_app(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data", llm_factory=_raise)
    client = TestClient(app)

    resp = client.post("/api/runs", json={"goal": "Find dentists"})
    assert resp.status_code == 400
    assert "GEMINI_API_KEY" in resp.json()["error"]

    resp2 = client.post("/api/learn")
    assert resp2.status_code == 400


def test_label_then_summary(tmp_path):
    app = create_app(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data", llm_factory=lambda: ScriptedLLM([]))
    client = TestClient(app)

    lead = Lead(id="osm:node/1", name="Clinic 1", niche="dentist", lat=1.0, lon=1.0)
    run_dir = tmp_path / "runs" / "run_test1"
    run_dir.mkdir(parents=True)
    state = {
        "run_id": "run_test1", "goal": "test goal", "plan": [], "step_log": [],
        "leads": {lead.id: lead.to_dict()}, "notes": [], "status": "done", "final_answer": "",
        "place": "", "bbox": None, "niches": [], "target_count": 0,
    }
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

    resp = client.post("/api/labels", json={"run_id": "run_test1", "lead_id": lead.id, "label": "good"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # a run's detail endpoint reflects the label.
    run_data = client.get("/api/runs/run_test1").json()
    assert run_data["labels"] == {lead.id: "good"}

    summary = client.get("/api/labels/summary").json()
    assert summary == {"total": 1, "good": 1, "bad": 0, "ready": False, "need": summary["need"]}
    assert "11 more" in summary["need"]
    assert "bad" in summary["need"]

    # bad label input is rejected.
    bad_resp = client.post("/api/labels", json={"run_id": "run_test1", "lead_id": lead.id, "label": "maybe"})
    assert bad_resp.status_code == 400

    # unknown run is 404.
    missing = client.post("/api/labels", json={"run_id": "nope", "lead_id": lead.id, "label": "good"})
    assert missing.status_code == 404

    # DELETE removes it.
    del_resp = client.delete(f"/api/labels/{lead.id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["removed"] is True
    summary2 = client.get("/api/labels/summary").json()
    assert summary2["total"] == 0


def test_learn_with_too_few_labels_returns_ok_false(tmp_path):
    app = create_app(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data", llm_factory=lambda: ScriptedLLM([]))
    client = TestClient(app)

    resp = client.post("/api/learn")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "Need at least" in body["message"]
    assert body["final_rules"] == []


def test_memory_endpoint(tmp_path):
    app = create_app(runs_dir=tmp_path / "runs", data_dir=tmp_path / "data", llm_factory=lambda: ScriptedLLM([]))
    client = TestClient(app)

    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json() == {"rules": [], "history": []}
