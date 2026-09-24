"""The agent loop: plan-and-execute with ReAct-style re-planning.

One LLM call turns a goal into a plan. Then the LLM repeatedly observes a
compact summary of state and picks the next tool call, until it calls
`finish` or the step budget runs out. Every step is persisted immediately so
a crashed or killed run leaves a readable trace.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from prospector import report as report_mod
from prospector import web
from prospector.llm import LLM, LLMError
from prospector.memory import Memory
from prospector.osm import BBox, Lead, NICHES, OSMError, geocode, search
from prospector.rules import score as score_lead

TRUNCATE_LEN = 1500
MAX_FAIL_REPEATS = 3
MAX_DEEP_RESEARCH = 8


def _truncate(text: str, limit: int = TRUNCATE_LEN) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + f"... [truncated, {len(text)} chars total]"


@dataclass
class Step:
    n: int
    thought: str
    action: str
    args: dict
    observation: str
    ok: bool
    ms: int

    def to_dict(self) -> dict:
        return {
            "n": self.n, "thought": self.thought, "action": self.action,
            "args": self.args, "observation": self.observation, "ok": self.ok, "ms": self.ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Step":
        return cls(**data)


@dataclass
class RunState:
    run_id: str
    goal: str
    plan: list[str] = field(default_factory=list)
    step_log: list[Step] = field(default_factory=list)
    leads: dict[str, Lead] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    status: str = "running"  # "running" | "done" | "failed" | "max_steps"
    final_answer: str = ""

    # Working state the tools read/write; not part of the contract's public
    # data-structure list, but needed to carry search context between steps.
    place: str = ""
    bbox: BBox | None = None
    niches: list[str] = field(default_factory=list)
    target_count: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "plan": self.plan,
            "step_log": [s.to_dict() for s in self.step_log],
            "leads": {lid: lead.to_dict() for lid, lead in self.leads.items()},
            "notes": self.notes,
            "status": self.status,
            "final_answer": self.final_answer,
            "place": self.place,
            "bbox": None if self.bbox is None else {
                "south": self.bbox.south, "west": self.bbox.west,
                "north": self.bbox.north, "east": self.bbox.east,
            },
            "niches": self.niches,
            "target_count": self.target_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        bbox_data = data.get("bbox")
        return cls(
            run_id=data["run_id"],
            goal=data["goal"],
            plan=data.get("plan", []),
            step_log=[Step.from_dict(s) for s in data.get("step_log", [])],
            leads={lid: Lead.from_dict(ld) for lid, ld in data.get("leads", {}).items()},
            notes=data.get("notes", []),
            status=data.get("status", "running"),
            final_answer=data.get("final_answer", ""),
            place=data.get("place", ""),
            bbox=BBox(**bbox_data) if bbox_data else None,
            niches=data.get("niches", []),
            target_count=data.get("target_count", 0),
        )


PLAN_SCHEMA_HINT = (
    '{"place": "<geocodable place name>", "niches": ["<niche key>", ...], '
    '"target_count": <int>, "plan": ["<step description>", ...]}'
)
LOOP_SCHEMA_HINT = '{"thought": "<reasoning>", "action": "<tool name>", "args": {...}}'


class Agent:
    def __init__(
        self,
        llm: LLM,
        memory: Memory,
        max_steps: int = 25,
        runs_dir: Path = Path("runs"),
        on_step: Callable[[Step, RunState], None] | None = None,
    ) -> None:
        self.llm = llm
        self.memory = memory
        self.max_steps = max_steps
        self.runs_dir = Path(runs_dir)
        self.on_step = on_step
        self._registry = self._build_registry()

    # -- Tool registry ----------------------------------------------------

    def _build_registry(self) -> dict[str, tuple[Callable, dict, str]]:
        return {
            "geocode": (
                self._tool_geocode,
                {"place": "string, optional (defaults to the planned place)"},
                "Resolve a place name to a bounding box.",
            ),
            "search_businesses": (
                self._tool_search_businesses,
                {"niches": "list[str], optional (defaults to planned niches)",
                 "limit": "int, optional (default 50)"},
                "Search OSM for businesses in the current bbox; appends new leads.",
            ),
            "widen_area": (
                self._tool_widen_area,
                {"factor": "float, optional (default 1.5)"},
                "Grow the current bbox around its center, e.g. after too few results.",
            ),
            "enrich": (
                self._tool_enrich,
                {"max_leads": "int, optional (default 20)"},
                "Fetch websites for up to max_leads not-yet-enriched leads (8 concurrent workers).",
            ),
            "score": (
                self._tool_score,
                {},
                "Score every lead with features + learned rules from memory (deterministic).",
            ),
            "deep_research": (
                self._tool_deep_research,
                {"lead_ids": f"list[str], max {MAX_DEEP_RESEARCH}"},
                "Fetch a deeper text snapshot of top leads' sites for hook writing.",
            ),
            "write_hooks": (
                self._tool_write_hooks,
                {"lead_ids": "list[str]"},
                "LLM writes a one-line pitch hook per lead, from observed facts only.",
            ),
            "finish": (
                self._tool_finish,
                {"summary": "string"},
                "End the run with a final summary.",
            ),
        }

    def _tool_geocode(self, state: RunState, args: dict) -> str:
        place = args.get("place") or state.place
        if not place:
            return "error: no place given and none planned"
        state.bbox = geocode(place)
        state.place = place
        return f"geocoded {place!r} to bbox=({state.bbox.south:.4f},{state.bbox.west:.4f},{state.bbox.north:.4f},{state.bbox.east:.4f})"

    def _tool_search_businesses(self, state: RunState, args: dict) -> str:
        if state.bbox is None:
            return "error: no bbox set; call geocode first"
        niches = args.get("niches") or state.niches
        niches = [n for n in niches if n in NICHES]
        if not niches:
            return "error: no valid niches to search (must be keys of osm.NICHES)"
        limit = int(args.get("limit") or 50)
        found = search(state.bbox, niches, limit)
        added = 0
        for lead in found:
            if lead.id not in state.leads:
                state.leads[lead.id] = lead
                added += 1
        return f"found {len(found)} businesses, {added} new (total leads: {len(state.leads)})"

    def _tool_widen_area(self, state: RunState, args: dict) -> str:
        if state.bbox is None:
            return "error: no bbox set; call geocode first"
        factor = float(args.get("factor") or 1.5)
        state.bbox = state.bbox.widened(factor)
        return f"widened bbox by factor {factor}: ({state.bbox.south:.4f},{state.bbox.west:.4f},{state.bbox.north:.4f},{state.bbox.east:.4f})"

    def _tool_enrich(self, state: RunState, args: dict) -> str:
        max_leads = int(args.get("max_leads") or 20)
        pending = [ld for ld in state.leads.values() if ld.site_ok is None and ld.fetch_error == ""]
        batch = pending[:max_leads]
        if not batch:
            return "no unenriched leads to process"
        enriched = web.enrich_all(batch, workers=8)
        for lead in enriched:
            state.leads[lead.id] = lead
        return f"enriched {len(enriched)} leads"

    def _tool_score(self, state: RunState, args: dict) -> str:
        rules = self.memory.load_rules()
        for lead in state.leads.values():
            s, reasons = score_lead(lead, rules)
            lead.score = s
            lead.reasons = reasons
        return f"scored {len(state.leads)} leads using {len(rules)} learned rule(s)"

    def _tool_deep_research(self, state: RunState, args: dict) -> str:
        lead_ids = list(args.get("lead_ids") or [])[:MAX_DEEP_RESEARCH]
        done = 0
        for lid in lead_ids:
            lead = state.leads.get(lid)
            if lead is None:
                continue
            lead.research = web.deep_research(lead)
            done += 1
        return f"deep-researched {done} lead(s)"

    def _tool_write_hooks(self, state: RunState, args: dict) -> str:
        lead_ids = list(args.get("lead_ids") or [])
        leads = [state.leads[lid] for lid in lead_ids if lid in state.leads]
        if not leads:
            return "no matching leads to write hooks for"

        facts_block = "\n".join(
            f"- {ld.id}: name={ld.name!r} niche={ld.niche!r} has_phone={bool(ld.phone)} "
            f"has_booking={ld.has_booking} chat_widget={ld.chat_widget!r} "
            f"reasons={ld.reasons} research_excerpt={ld.research.get('text_excerpt', '')[:300]!r}"
            for ld in leads
        )
        system = (
            "You write a single-sentence, concrete cold-outreach hook per lead for "
            "an AI phone receptionist product. Use ONLY facts given below -- never "
            "invent details not present in the facts."
        )
        user = f"Leads:\n{facts_block}\n\nWrite one hook sentence per lead id."
        schema_hint = '{"hooks": {"<lead_id>": "<one sentence hook>"}}'
        try:
            response = self.llm.json(system, user, schema_hint)
        except LLMError as exc:
            return f"error: hook generation failed: {exc}"

        hooks = response.get("hooks", {}) if isinstance(response, dict) else {}
        written = 0
        for lid, hook in hooks.items():
            if lid in state.leads and isinstance(hook, str):
                state.leads[lid].hook = hook
                written += 1
        return f"wrote {written} hook(s)"

    def _tool_finish(self, state: RunState, args: dict) -> str:
        state.final_answer = str(args.get("summary", ""))
        state.status = "done"
        return "run finished"

    # -- Persistence --------------------------------------------------------

    def _run_dir(self, run_id: str) -> Path:
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _persist_state(self, state: RunState) -> None:
        run_dir = self._run_dir(state.run_id)
        (run_dir / "state.json").write_text(
            json.dumps(state.to_dict(), indent=2), encoding="utf-8"
        )

    def _append_trace(self, state: RunState, step: Step) -> None:
        run_dir = self._run_dir(state.run_id)
        with (run_dir / "trace.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(step.to_dict()) + "\n")

    def _write_final_outputs(self, state: RunState) -> None:
        run_dir = self._run_dir(state.run_id)
        report_mod.write_leads_csv(state, run_dir / "leads.csv")
        report_mod.write_report(state, self.memory, run_dir / "report.md")

    # -- State summary for the LLM ------------------------------------------

    def _state_summary(self, state: RunState) -> str:
        leads = state.leads.values()
        found = len(state.leads)
        enriched = sum(1 for ld in leads if ld.site_ok is not None or ld.fetch_error != "")
        researched = sum(1 for ld in state.leads.values() if ld.research)
        scored = sum(1 for ld in state.leads.values() if ld.reasons)

        last_observations = [
            f"step {s.n}: {s.action}({s.args}) -> {'ok' if s.ok else 'FAIL'}: {s.observation}"
            for s in state.step_log[-3:]
        ]

        tools_desc = "\n".join(
            f"- {name}(args={schema}): {desc}"
            for name, (_, schema, desc) in self._registry.items()
        )

        notes = "\n".join(state.notes) if state.notes else "(none)"

        return (
            f"Counts: found={found}, enriched={enriched}, researched={researched}, scored={scored}\n"
            f"Last observations:\n" + ("\n".join(last_observations) or "(none yet)") + "\n\n"
            f"Notes:\n{notes}\n\n"
            f"Available tools:\n{tools_desc}"
        )

    # -- Main loop --------------------------------------------------------

    def run(self, goal: str) -> RunState:
        run_id = f"run_{int(time.time())}"
        state = RunState(run_id=run_id, goal=goal)

        # 1. PLAN
        try:
            plan_response = self.llm.json(
                system=(
                    "You are a planning module for a lead-prospecting agent. Turn the "
                    "goal into a place, a list of business niches, a target lead count, "
                    "and a short numbered plan. `niches` entries MUST be chosen from the "
                    "known niche keys; map anything close to the nearest known key, or "
                    "omit it if nothing is close."
                ),
                user=f"Goal: {goal}\n\nKnown niche keys: {sorted(NICHES.keys())}",
                schema_hint=PLAN_SCHEMA_HINT,
            )
        except LLMError as exc:
            state.status = "failed"
            state.notes.append(f"planning failed: {exc}")
            self._persist_state(state)
            self._write_final_outputs(state)
            return state

        state.place = str(plan_response.get("place", "")).strip()
        requested_niches = plan_response.get("niches", []) or []
        valid_niches = [n for n in requested_niches if n in NICHES]
        dropped = [n for n in requested_niches if n not in NICHES]
        if dropped:
            state.notes.append(f"plan requested unknown niches, dropped: {dropped}")
        state.niches = valid_niches
        state.target_count = int(plan_response.get("target_count") or 0)
        state.plan = list(plan_response.get("plan", []))
        self._persist_state(state)

        # 2. LOOP
        fail_counts: dict[tuple[str, str], int] = {}
        blocked: set[tuple[str, str]] = set()

        for n in range(1, self.max_steps + 1):
            start = time.monotonic()
            try:
                decision = self.llm.json(
                    system=(
                        "You are the acting module of a lead-prospecting agent using "
                        "plan-and-execute with ReAct-style re-planning. Given the goal, "
                        "plan, and current state, choose exactly one next tool call. "
                        "React to failures and low result counts by changing approach "
                        "(e.g. widen_area). Call finish once the goal is satisfied."
                    ),
                    user=(
                        f"Goal: {goal}\nPlan: {state.plan}\n\n{self._state_summary(state)}"
                    ),
                    schema_hint=LOOP_SCHEMA_HINT,
                )
            except LLMError as exc:
                state.status = "failed"
                state.notes.append(f"acting failed at step {n}: {exc}")
                self._persist_state(state)
                break

            thought = str(decision.get("thought", ""))
            action = str(decision.get("action", ""))
            args = decision.get("args") or {}
            args_key = (action, json.dumps(args, sort_keys=True, default=str))

            if args_key in blocked:
                observation = f"blocked: action {action!r} with these args failed {MAX_FAIL_REPEATS}x in a row"
                ok = False
            elif action not in self._registry:
                observation = f"unknown action {action!r}; available: {sorted(self._registry.keys())}"
                ok = False
            else:
                fn, _, _ = self._registry[action]
                try:
                    observation = fn(state, args)
                    ok = not observation.startswith("error:")
                except Exception as exc:  # noqa: BLE001 - a tool failure is an observation, not a crash
                    observation = f"error: {type(exc).__name__}: {exc}"
                    ok = False

            ms = int((time.monotonic() - start) * 1000)
            step = Step(n=n, thought=thought, action=action, args=args,
                        observation=_truncate(observation), ok=ok, ms=ms)
            state.step_log.append(step)

            if ok:
                fail_counts[args_key] = 0
            else:
                fail_counts[args_key] = fail_counts.get(args_key, 0) + 1
                if fail_counts[args_key] >= MAX_FAIL_REPEATS and args_key not in blocked:
                    blocked.add(args_key)
                    state.notes.append(
                        f"action {action!r} with args {args} failed {MAX_FAIL_REPEATS}x in a row; blocking it"
                    )

            self._persist_state(state)
            self._append_trace(state, step)
            if self.on_step:
                self.on_step(step, state)

            if action == "finish" and ok:
                break
        else:
            # `for...else` runs only if the loop completed without `break`,
            # i.e. the step budget ran out before `finish` was called.
            state.status = "max_steps"
            state.notes.append(f"reached max_steps ({self.max_steps}) without finishing")

        self._persist_state(state)
        self._write_final_outputs(state)
        return state
