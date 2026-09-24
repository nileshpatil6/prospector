import json

import pytest

from prospector import agent as agent_mod
from prospector.agent import Agent
from prospector.llm import ScriptedLLM
from prospector.memory import Memory
from prospector.osm import BBox, Lead


def _fake_lead(n: int) -> Lead:
    return Lead(id=f"osm:node/{n}", name=f"Clinic {n}", niche="dentist", lat=18.5, lon=73.8)


def test_full_flow_with_replan_after_low_results(tmp_path, monkeypatch):
    call_count = {"search": 0}

    def fake_geocode(place):
        return BBox(south=18.4, west=73.7, north=18.6, east=73.9)

    def fake_search(bbox, niches, limit):
        call_count["search"] += 1
        if call_count["search"] == 1:
            return [_fake_lead(1), _fake_lead(2)]  # too few vs target_count=10
        return [_fake_lead(1), _fake_lead(2), _fake_lead(3), _fake_lead(4), _fake_lead(5)]

    monkeypatch.setattr(agent_mod, "geocode", fake_geocode)
    monkeypatch.setattr(agent_mod, "search", fake_search)

    responses = [
        # PLAN
        {"place": "Pune, India", "niches": ["dentist"], "target_count": 10,
         "plan": ["geocode", "search", "widen if needed", "score", "finish"]},
        # LOOP
        {"thought": "geocode the place", "action": "geocode", "args": {}},
        {"thought": "search for dentists", "action": "search_businesses",
         "args": {"niches": ["dentist"], "limit": 50}},
        {"thought": "too few results, widen the area", "action": "widen_area", "args": {"factor": 1.5}},
        {"thought": "search again", "action": "search_businesses",
         "args": {"niches": ["dentist"], "limit": 50}},
        {"thought": "score everything", "action": "score", "args": {}},
        {"thought": "done", "action": "finish", "args": {"summary": "found 5 dentist leads"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=10, runs_dir=tmp_path / "runs")

    state = agent.run("Find 10 dentists in Pune")

    assert state.status == "done"
    assert state.final_answer == "found 5 dentist leads"
    assert len(state.leads) == 5
    assert call_count["search"] == 2  # re-planned and searched again after low results
    assert all(ld.reasons for ld in state.leads.values())  # score tool ran

    # state.json persisted after every step, matching final step count.
    state_path = tmp_path / "runs" / state.run_id / "state.json"
    assert state_path.exists()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "done"
    assert len(persisted["step_log"]) == len(state.step_log) == 6

    trace_path = tmp_path / "runs" / state.run_id / "trace.jsonl"
    trace_lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(trace_lines) == 6

    assert (tmp_path / "runs" / state.run_id / "leads.csv").exists()
    assert (tmp_path / "runs" / state.run_id / "report.md").exists()


def test_unknown_action_is_an_observation_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))

    responses = [
        {"place": "Nowhere", "niches": [], "target_count": 1, "plan": []},
        {"thought": "try something weird", "action": "fly_to_moon", "args": {}},
        {"thought": "give up gracefully", "action": "finish", "args": {"summary": "nothing found"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find nothing")

    assert state.status == "done"
    bad_step = state.step_log[0]
    assert bad_step.action == "fly_to_moon"
    assert bad_step.ok is False
    assert "unknown action" in bad_step.observation


def test_max_steps_path_writes_partial_results(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))

    responses = [
        {"place": "Pune", "niches": ["dentist"], "target_count": 100, "plan": ["search forever"]},
        {"thought": "geocode", "action": "geocode", "args": {}},
        {"thought": "geocode again", "action": "geocode", "args": {}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=2, runs_dir=tmp_path / "runs")

    state = agent.run("Find 100 dentists in Pune")

    assert state.status == "max_steps"
    assert len(state.step_log) == 2
    assert any("max_steps" in note for note in state.notes)
    assert (tmp_path / "runs" / state.run_id / "leads.csv").exists()
    assert (tmp_path / "runs" / state.run_id / "report.md").exists()


def test_max_steps_finalize_scores_unscored_leads(tmp_path, monkeypatch):
    # MED regression: a run that hits max_steps before ever calling `score`
    # must not ship a report where every lead sits at score=0/no reasons.
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    monkeypatch.setattr(agent_mod, "search", lambda bbox, niches, limit: [_fake_lead(1), _fake_lead(2)])

    responses = [
        {"place": "Pune", "niches": ["dentist"], "target_count": 5, "plan": []},
        {"thought": "geocode", "action": "geocode", "args": {}},
        {"thought": "search", "action": "search_businesses", "args": {"niches": ["dentist"], "limit": 50}},
        # Never reaches `score` or `finish` -- max_steps cuts it off here.
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=2, runs_dir=tmp_path / "runs")

    state = agent.run("Find 5 dentists in Pune")

    assert state.status == "max_steps"
    assert len(state.leads) == 2
    assert all(ld.reasons for ld in state.leads.values())  # finalize() ran score


def test_repeated_failing_action_gets_blocked(tmp_path, monkeypatch):
    def failing_search(bbox, niches, limit):
        raise RuntimeError("overpass is down")

    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    monkeypatch.setattr(agent_mod, "search", failing_search)

    same_search = {"thought": "search", "action": "search_businesses", "args": {"niches": ["dentist"], "limit": 50}}
    responses = [
        {"place": "Pune", "niches": ["dentist"], "target_count": 5, "plan": []},
        {"thought": "geocode", "action": "geocode", "args": {}},
        same_search, same_search, same_search,
        {"thought": "give up", "action": "finish", "args": {"summary": "overpass unavailable"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=10, runs_dir=tmp_path / "runs")

    state = agent.run("Find 5 dentists in Pune")

    fail_steps = [s for s in state.step_log if s.action == "search_businesses"]
    assert len(fail_steps) == 3
    assert all(not s.ok for s in fail_steps)
    assert any("blocking it" in note for note in state.notes)


# --- HIGH: odd-but-technically-valid LLM output must never crash run() ----

def test_plan_niches_as_single_string_is_wrapped_not_split_into_chars(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        # niches is a bare string, not a list -- must become ["dentist"],
        # never iterated into ["d", "e", "n", "t", ...].
        {"place": "Pune", "niches": "dentist", "target_count": "30 leads", "plan": "just go"},
        {"thought": "done immediately", "action": "finish", "args": {"summary": "ok"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find 30 dentists in Pune")

    assert state.status == "done"
    assert state.niches == ["dentist"]
    assert state.target_count == 30  # regex-parsed out of "30 leads"
    assert state.plan == ["just go"]  # a bare string plan wrapped into a list


def test_plan_niche_item_that_is_a_dict_is_dropped_not_crashed(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        {"place": "Pune", "niches": ["dentist", {"weird": "object"}], "target_count": 5, "plan": []},
        {"thought": "done", "action": "finish", "args": {"summary": "ok"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find dentists")

    assert state.status == "done"
    assert state.niches == ["dentist"]
    assert any("dropped" in note for note in state.notes)


def test_plan_target_count_as_words_defaults_or_parses_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        {"place": "Pune", "niches": [], "target_count": "a lot, maybe 12ish", "plan": []},
        {"thought": "done", "action": "finish", "args": {"summary": "ok"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find some dentists")

    assert state.status == "done"
    assert state.target_count == 12  # first digit run found by the regex parse


def test_loop_args_not_an_object_becomes_failed_step_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        {"place": "Pune", "niches": [], "target_count": 1, "plan": []},
        # args is a list instead of an object.
        {"thought": "weird", "action": "geocode", "args": ["Pune"]},
        {"thought": "recover", "action": "finish", "args": {"summary": "ok"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find dentists")

    assert state.status == "done"
    bad_step = state.step_log[0]
    assert bad_step.ok is False
    assert "args was not an object" in bad_step.observation
    assert state.step_log[1].action == "finish"


def test_decision_that_is_not_a_dict_is_a_failed_step_not_a_crash(tmp_path, monkeypatch):
    # ScriptedLLM enforces dict-or-raise itself (mirroring the GeminiLLM.json
    # contract tested directly in test_llm.py), so a non-dict "decision" from
    # the LLM layer surfaces as an LLMError here. run() must record that as a
    # failed step and keep going rather than propagate the exception --
    # until MAX_CONSECUTIVE_LLM_FAILURES is hit.
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        {"place": "Pune", "niches": [], "target_count": 1, "plan": []},
        ["not", "a", "dict"],  # the "decision" -- ScriptedLLM.json rejects this
        {"thought": "recover", "action": "finish", "args": {"summary": "ok"}},
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find dentists")

    assert state.status == "done"
    assert state.step_log[0].ok is False
    assert "LLM call failed" in state.step_log[0].observation
    assert state.step_log[1].action == "finish"


def test_two_consecutive_llm_failures_marks_run_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "geocode", lambda place: BBox(0, 0, 1, 1))
    responses = [
        {"place": "Pune", "niches": [], "target_count": 1, "plan": []},
        ["bad", "decision", "one"],
        ["bad", "decision", "two"],
    ]
    llm = ScriptedLLM(responses)
    memory = Memory(tmp_path / "data")
    agent = Agent(llm, memory, max_steps=5, runs_dir=tmp_path / "runs")

    state = agent.run("Find dentists")

    assert state.status == "failed"
    assert len(state.step_log) == 2
    assert all(not s.ok for s in state.step_log)
    # Never crashed: run() returned a RunState, and outputs were still written.
    assert (tmp_path / "runs" / state.run_id / "leads.csv").exists()
    assert (tmp_path / "runs" / state.run_id / "report.md").exists()


# --- HIGH: the LLM must see real lead ids so deep_research/write_hooks can
# actually target something ------------------------------------------------

def test_state_summary_includes_top_lead_ids_and_website_flag(tmp_path):
    memory = Memory(tmp_path / "data")
    agent = Agent(ScriptedLLM([]), memory, runs_dir=tmp_path / "runs")

    from prospector.agent import RunState
    state = RunState(run_id="r1", goal="test")
    state.leads["osm:node/1"] = _fake_lead(1)
    state.leads["osm:node/1"].website = "https://example.com"
    state.leads["osm:node/1"].score = 80.0
    state.leads["osm:node/2"] = _fake_lead(2)
    state.leads["osm:node/2"].score = 40.0

    summary = agent._state_summary(state)

    assert "osm:node/1" in summary
    assert "osm:node/2" in summary
    assert "80" in summary
    # website yes/no column reflects whether each lead actually has one.
    lines = {line.split(" | ")[0]: line for line in summary.splitlines() if " | " in line}
    assert lines["osm:node/1"].strip().endswith("yes")
    assert lines["osm:node/2"].strip().endswith("no")


def test_deep_research_falls_back_to_top_scored_leads_when_ids_missing(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "data")
    agent = Agent(ScriptedLLM([]), memory, runs_dir=tmp_path / "runs")

    from prospector.agent import RunState
    state = RunState(run_id="r1", goal="test")
    low = _fake_lead(1); low.score = 10.0
    high = _fake_lead(2); high.score = 90.0
    state.leads[low.id] = low
    state.leads[high.id] = high

    monkeypatch.setattr(agent_mod.web, "deep_research", lambda lead, timeout=10: {"title": "ok"})

    observation = agent._tool_deep_research(state, {})  # no lead_ids given at all

    assert not observation.startswith("error:")
    assert high.research == {"title": "ok"}
    assert low.research == {"title": "ok"}


def test_deep_research_errors_with_ok_false_when_no_leads_at_all(tmp_path):
    memory = Memory(tmp_path / "data")
    agent = Agent(ScriptedLLM([]), memory, runs_dir=tmp_path / "runs")

    from prospector.agent import RunState
    state = RunState(run_id="r1", goal="test")  # no leads

    observation = agent._tool_deep_research(state, {"lead_ids": ["nope"]})

    assert observation.startswith("error:")
