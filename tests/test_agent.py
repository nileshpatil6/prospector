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
