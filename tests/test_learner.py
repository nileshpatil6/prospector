import random

from prospector.learner import MIN_LABELS, _is_holdout, learn
from prospector.llm import ScriptedLLM
from prospector.memory import Memory
from prospector.osm import Lead

NICHE_SAMPLE = ["dentist", "restaurant"]
CHAT_SAMPLE = ["", "tidio", "drift"]


def _make_lead(i: int, has_booking: bool, rng: random.Random) -> Lead:
    return Lead(
        id=f"learn_lead_{i}",
        name=f"Biz {i}",
        niche=rng.choice(NICHE_SAMPLE),
        lat=0.0, lon=0.0,
        phone="555-0000",  # constant: no ordering signal
        website="https://example.com" if rng.random() < 0.8 else "",
        emails=["a@example.com"] if rng.random() < 0.5 else [],
        has_booking=has_booking,
        chat_widget=rng.choice(CHAT_SAMPLE),
        has_contact_form=True,
        site_ok=rng.random() < 0.5,
        opening_hours="Mo-Fr 09:00-18:00" if rng.random() < 0.7 else "",
    )


def _seed_labels(memory: Memory, n_per_class: int = 20) -> None:
    rng = random.Random(20260925)
    i = 0
    for has_booking, label in ((True, "bad"), (False, "good")):
        for _ in range(n_per_class):
            lead = _make_lead(i, has_booking, rng)
            memory.add_label(lead, label, run_id="seed_run")
            i += 1


def test_learn_no_op_below_min_labels(tmp_path):
    memory = Memory(tmp_path / "data")
    rng = random.Random(1)
    for i in range(5):
        lead = _make_lead(i, has_booking=(i % 2 == 0), rng=rng)
        memory.add_label(lead, "good" if i % 2 else "bad", run_id="r0")

    llm = ScriptedLLM([])  # must not be called at all
    report = learn(memory, llm)

    assert report.ok is False
    assert "12" in report.message or str(MIN_LABELS) in report.message
    assert llm.calls == []
    assert memory.load_rules() == []


def test_learn_keeps_good_rule_rejects_invalid_and_harmful(tmp_path):
    memory = Memory(tmp_path / "data")
    _seed_labels(memory, n_per_class=25)

    candidate_response = {
        "rules": [
            {"feature": "has_booking", "op": "is_false", "value": None, "weight": 25,
             "rationale": "no online booking predicts a good AI-receptionist fit"},
            {"feature": "warp_speed", "op": "==", "value": True, "weight": 5,
             "rationale": "nonsense feature that does not exist"},
            {"feature": "has_booking", "op": "is_true", "value": None, "weight": 20,
             "rationale": "harmful: rewards leads that already have booking"},
        ]
    }
    llm = ScriptedLLM([candidate_response])

    holdout_ids = {
        f"learn_lead_{i}" for i in range(50) if _is_holdout(f"learn_lead_{i}")
    }

    report = learn(memory, llm)

    assert report.ok is True
    assert report.n_labels == 50
    assert report.n_holdout == len(holdout_ids)

    added_features = [(r.feature, r.op) for r in report.added]
    assert ("has_booking", "is_false") in added_features

    rejected_features = [(r["rule"]["feature"], r["rule"]["op"]) for r in report.rejected]
    assert ("warp_speed", "==") in rejected_features
    warp_reason = next(r["reason"] for r in report.rejected if r["rule"]["feature"] == "warp_speed")
    assert "unknown feature" in warp_reason

    assert ("has_booking", "is_true") in rejected_features

    assert report.acc_after > report.acc_before

    # INVARIANT: the LLM prompt must never contain a holdout lead's id.
    assert len(llm.calls) == 1
    _, _, user_prompt = llm.calls[0]
    for hid in holdout_ids:
        assert hid not in user_prompt

    # Rules persisted to disk.
    saved = memory.load_rules()
    assert any(r.feature == "has_booking" and r.op == "is_false" for r in saved)

    history = memory.get_history()
    assert len(history) == 1
    assert history[0]["acc_after"] >= history[0]["acc_before"]
