"""FastAPI backend for Prospector: runs, labels, and learning.

Replaces the Streamlit UI (app.py). A run executes in a background thread so
the HTTP request returns immediately with a run_id; the Next.js frontend
polls GET /api/runs/{id} once a second while status == "running". Only one
run may be active at a time (409 otherwise).

Run with: uvicorn server:app --port 8000
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from prospector.agent import Agent
from prospector.learner import MIN_LABELS, learn
from prospector.live import LiveSessionError, create_live_session
from prospector.llm import LLM, GeminiLLM, LLMError
from prospector.memory import Memory
from prospector.osm import Lead

load_dotenv()

_RUN_ID_TS_RE = re.compile(r"(\d+)$")


def _read_json_retrying(path: Path, attempts: int = 20, delay: float = 0.02) -> dict:
    """Read and parse a JSON file, retrying briefly on a decode error.

    Agent._persist_state() rewrites state.json on every step with a plain
    write_text (open, write, close) -- not an atomic replace -- so a poll
    landing mid-write can see a truncated file. That's a transient race, not
    a real error, so a short retry loop is used instead of surfacing a 500."""
    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            last_exc = exc
            time.sleep(delay)
    raise HTTPException(500, f"could not read {path}: {last_exc}")


def _started_at(run_id: str) -> float:
    """run_id is f"run_{int(time.time())}" -- pull the epoch back out so the
    runs list can be sorted newest-first without trusting directory mtimes
    (which can be rewritten by e.g. a git checkout)."""
    match = _RUN_ID_TS_RE.search(run_id)
    return float(match.group(1)) if match else 0.0


def _describe_need(total: int, good: int, bad: int) -> str:
    """Plain-words description of what's missing before `learn` will run,
    mirroring the gate in learner.learn() (MIN_LABELS, at least one of each
    class)."""
    missing_classes = []
    if good == 0:
        missing_classes.append("good")
    if bad == 0:
        missing_classes.append("bad")
    remaining = max(0, MIN_LABELS - total)

    if remaining > 0:
        text = f"{remaining} more"
        if missing_classes:
            text += f" incl. at least 1 {' and '.join(missing_classes)}"
        return text
    if missing_classes:
        return f"at least 1 {' and '.join(missing_classes)} label"
    return ""


def _load_run_and_lead(runs_dir: Path, run_id: str, lead_id: str) -> tuple[dict, dict]:
    """Load a run's state.json and pick out one lead's raw dict, or raise the
    404 both /live-session and /messages need on an unknown run/lead."""
    state_path = runs_dir / run_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, f"run {run_id!r} not found")
    data = _read_json_retrying(state_path)
    lead_data = data.get("leads", {}).get(lead_id)
    if lead_data is None:
        raise HTTPException(404, f"lead {lead_id!r} not found in run {run_id!r}")
    return data, lead_data


class RunRequest(BaseModel):
    goal: str
    max_steps: int | None = None


class LabelRequest(BaseModel):
    run_id: str
    lead_id: str
    label: str


class MessageRequest(BaseModel):
    caller_name: str
    callback_number: str
    reason: str


MAX_MESSAGE_FIELD_LEN = 200


def create_app(
    runs_dir: Path = Path("runs"),
    data_dir: Path = Path("data"),
    llm_factory: Callable[[], LLM] | None = None,
) -> FastAPI:
    """Build a FastAPI app bound to the given runs/data directories and LLM
    factory. A factory function (not a fixed instance) so tests can inject a
    ScriptedLLM per-request, and so a missing GEMINI_API_KEY surfaces as a
    400 at request time rather than crashing app startup."""
    app = FastAPI(title="Prospector API")

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        # Deployed frontends, e.g. CORS_ORIGINS=https://prospector.vercel.app
        allow_origins=[o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.runs_dir = Path(runs_dir)
    app.state.data_dir = Path(data_dir)
    app.state.memory = Memory(app.state.data_dir)
    app.state.llm_factory = llm_factory or GeminiLLM
    app.state.active_run_id = None
    app.state.lock = threading.Lock()

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    # -- Runs -------------------------------------------------------------

    @app.post("/api/runs")
    def create_run(req: RunRequest) -> dict:
        goal = req.goal.strip()
        if not goal:
            raise HTTPException(400, "goal must not be empty")

        with app.state.lock:
            if app.state.active_run_id is not None:
                raise HTTPException(409, "a run is already active")
            try:
                llm = app.state.llm_factory()
            except LLMError as exc:
                raise HTTPException(400, str(exc))
            run_id = f"run_{int(time.time())}"
            app.state.active_run_id = run_id
            app.state.active_goal = goal

        agent = Agent(
            llm, app.state.memory,
            max_steps=req.max_steps or 25,
            runs_dir=app.state.runs_dir,
        )

        def _worker() -> None:
            try:
                agent.run(goal, run_id=run_id)
            finally:
                with app.state.lock:
                    if app.state.active_run_id == run_id:
                        app.state.active_run_id = None

        threading.Thread(target=_worker, daemon=True).start()
        return {"run_id": run_id}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        items: list[dict] = []
        runs_dir = app.state.runs_dir
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                state_path = run_dir / "state.json"
                if not run_dir.is_dir() or not state_path.exists():
                    continue
                try:
                    data = json.loads(state_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                run_id = data.get("run_id", run_dir.name)
                items.append({
                    "run_id": run_id,
                    "goal": data.get("goal", ""),
                    "status": data.get("status", "unknown"),
                    "n_leads": len(data.get("leads", {})),
                    "started_at": _started_at(run_id),
                })
        items.sort(key=lambda it: it["started_at"], reverse=True)
        return items

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        state_path = app.state.runs_dir / run_id / "state.json"
        if not state_path.exists():
            # The run's first state.json is written after the planning LLM
            # call, so a client polling right after POST /api/runs would
            # otherwise see a 404 for a run that is in fact starting.
            if run_id == app.state.active_run_id:
                return {"run_id": run_id, "goal": getattr(app.state, "active_goal", ""),
                        "plan": [], "step_log": [], "leads": {}, "notes": [],
                        "status": "running", "final_answer": "", "labels": {}}
            raise HTTPException(404, f"run {run_id!r} not found")
        data = _read_json_retrying(state_path)
        lead_ids = set(data.get("leads", {}).keys())
        data["labels"] = {
            r["lead_id"]: r["label"] for r in app.state.memory.get_labels() if r["lead_id"] in lead_ids
        }
        return data

    @app.get("/api/runs/{run_id}/report")
    def get_report(run_id: str) -> PlainTextResponse:
        report_path = app.state.runs_dir / run_id / "report.md"
        if not report_path.exists():
            raise HTTPException(404, f"report not found for run {run_id!r}")
        return PlainTextResponse(report_path.read_text(encoding="utf-8"), media_type="text/markdown")

    @app.get("/api/runs/{run_id}/csv")
    def get_csv(run_id: str) -> Response:
        csv_path = app.state.runs_dir / run_id / "leads.csv"
        if not csv_path.exists():
            raise HTTPException(404, f"csv not found for run {run_id!r}")
        return Response(
            content=csv_path.read_bytes(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{run_id}_leads.csv"'},
        )

    # -- Labels -------------------------------------------------------------

    @app.post("/api/labels")
    def create_label(req: LabelRequest) -> dict:
        if req.label not in ("good", "bad"):
            raise HTTPException(400, "label must be 'good' or 'bad'")
        state_path = app.state.runs_dir / req.run_id / "state.json"
        if not state_path.exists():
            raise HTTPException(404, f"run {req.run_id!r} not found")
        data = _read_json_retrying(state_path)
        lead_data = data.get("leads", {}).get(req.lead_id)
        if lead_data is None:
            raise HTTPException(404, f"lead {req.lead_id!r} not found in run {req.run_id!r}")
        lead = Lead.from_dict(lead_data)
        app.state.memory.add_label(lead, req.label, req.run_id)
        return {"ok": True}

    @app.delete("/api/labels/{lead_id:path}")
    def delete_label(lead_id: str) -> dict:
        # lead_id is e.g. "osm:way/12345" -- the ":path" converter is needed
        # so the embedded "/" doesn't get parsed as an extra path segment.
        removed = app.state.memory.remove_label(lead_id)
        return {"ok": True, "removed": removed}

    @app.get("/api/labels/summary")
    def labels_summary() -> dict:
        labels = app.state.memory.get_labels()
        total = len(labels)
        good = sum(1 for r in labels if r["label"] == "good")
        bad = total - good
        ready = total >= MIN_LABELS and good > 0 and bad > 0
        return {
            "total": total,
            "good": good,
            "bad": bad,
            "ready": ready,
            "need": "" if ready else _describe_need(total, good, bad),
        }

    # -- Live receptionist ---------------------------------------------------

    @app.post("/api/runs/{run_id}/leads/{lead_id:path}/live-session")
    def create_live_session_route(run_id: str, lead_id: str) -> dict:
        _data, lead_data = _load_run_and_lead(app.state.runs_dir, run_id, lead_id)
        lead = Lead.from_dict(lead_data)
        try:
            return create_live_session(lead)
        except LiveSessionError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/runs/{run_id}/leads/{lead_id:path}/messages")
    def create_message_route(run_id: str, lead_id: str, req: MessageRequest) -> dict:
        for field_name in ("caller_name", "callback_number", "reason"):
            if len(getattr(req, field_name)) > MAX_MESSAGE_FIELD_LEN:
                raise HTTPException(400, f"{field_name} must be at most {MAX_MESSAGE_FIELD_LEN} chars")

        state_path = app.state.runs_dir / run_id / "state.json"
        data, lead_data = _load_run_and_lead(app.state.runs_dir, run_id, lead_id)
        message = {
            "caller_name": req.caller_name,
            "callback_number": req.callback_number,
            "reason": req.reason,
            "ts": time.time(),
        }
        lead_data.setdefault("messages", []).append(message)
        data["leads"][lead_id] = lead_data
        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return message

    # -- Learning -------------------------------------------------------------

    @app.post("/api/learn")
    def run_learn() -> dict:
        try:
            llm = app.state.llm_factory()
        except LLMError as exc:
            raise HTTPException(400, str(exc))
        report = learn(app.state.memory, llm)
        return {
            "ok": report.ok,
            "message": report.message,
            "n_labels": report.n_labels,
            "n_train": report.n_train,
            "n_holdout": report.n_holdout,
            "acc_before": report.acc_before,
            "acc_after": report.acc_after,
            "p_at_10_before": report.p_at_10_before,
            "p_at_10_after": report.p_at_10_after,
            "added": [r.to_dict() for r in report.added],
            "removed": [r.to_dict() for r in report.removed],
            "rejected": report.rejected,
            "final_rules": [r.to_dict() for r in report.final_rules],
        }

    @app.get("/api/memory")
    def get_memory() -> dict:
        return {
            "rules": [r.to_dict() for r in app.state.memory.load_rules()],
            "history": app.state.memory.get_history(),
        }

    return app


app = create_app()
