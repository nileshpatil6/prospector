import random

from prospector.learner import MIN_LABELS, MIN_SPLIT_SIZE, _bucket, _parse_candidates, _split3, _threshold, learn
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


def _seed_labels(memory: Memory, n_bad: int, n_good: int, prefix: str = "learn_lead") -> None:
    rng = random.Random(20260925)
    i = 0
    for has_booking, label, count in ((True, "bad", n_bad), (False, "good", n_good)):
        for _ in range(count):
            lead = _make_lead(i, has_booking, rng)
            lead.id = f"{prefix}_{i}"
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
    _seed_labels(memory, n_bad=25, n_good=25)

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

    labels = memory.get_labels()
    _, select, test = _split3(labels)
    held_out_ids = {r["lead_id"] for r in select} | {r["lead_id"] for r in test}

    report = learn(memory, llm)

    assert report.ok is True
    assert report.n_labels == 50

    added_features = [(r.feature, r.op) for r in report.added]
    assert ("has_booking", "is_false") in added_features

    rejected_features = [(r["rule"]["feature"], r["rule"]["op"]) for r in report.rejected]
    assert ("warp_speed", "==") in rejected_features
    warp_reason = next(r["reason"] for r in report.rejected if r["rule"]["feature"] == "warp_speed")
    assert "unknown feature" in warp_reason

    assert ("has_booking", "is_true") in rejected_features

    assert report.acc_after > report.acc_before

    # INVARIANT: the LLM prompt must never contain a select/test lead's id.
    assert len(llm.calls) == 1
    _, _, user_prompt = llm.calls[0]
    for hid in held_out_ids:
        assert hid not in user_prompt

    # Rules persisted to disk.
    saved = memory.load_rules()
    assert any(r.feature == "has_booking" and r.op == "is_false" for r in saved)

    history = memory.get_history()
    assert len(history) == 1
    assert history[0]["acc_after"] >= history[0]["acc_before"]


# --- HIGH: _threshold tie-breaking (a perfectly separating rule must not be
# rejected just because a naive median+">=" puts a tied cluster on the wrong
# side) -----------------------------------------------------------------

def _lead_record(lead_id: str, has_booking: bool, label: str) -> dict:
    """A minimal train/select/test record whose base_score() is exactly
    computable: has_phone (+30) always fires, no_online_booking (+20) fires
    only when has_booking is False, and nothing else about this lead
    contributes -- so score is either exactly 30 (has_booking) or 50 (not)."""
    lead = Lead(
        id=lead_id, name="Biz", niche="restaurant", lat=0.0, lon=0.0,
        phone="555-0000", website="https://example.com", emails=[],
        has_booking=has_booking, chat_widget="", has_contact_form=None,
        site_ok=None, opening_hours="",
    )
    return {"lead_id": lead_id, "label": label, "lead": lead.to_dict(), "features": {}}


def test_threshold_finds_separator_despite_median_tie():
    # 8 "bad" leads all score exactly 30; 4 "good" leads all score exactly
    # 50. A plain median of the 12 sorted scores lands on 30 (the tied
    # cluster), and with ">=" that predicts "good" for every single lead
    # (33% accuracy) even though a perfect separator (any threshold in
    # (30, 50]) exists.
    train = (
        [_lead_record(f"bad_{i}", has_booking=True, label="bad") for i in range(8)]
        + [_lead_record(f"good_{i}", has_booking=False, label="good") for i in range(4)]
    )

    threshold = _threshold(rules=[], train=train)

    correct = 0
    for record in train:
        lead = Lead.from_dict(record["lead"])
        from prospector.rules import score as score_fn
        predicted = "good" if score_fn(lead, [])[0] >= threshold else "bad"
        correct += predicted == record["label"]

    assert 30.0 < threshold <= 50.0, f"threshold {threshold} did not separate the tied clusters"
    assert correct == len(train)  # 100% train accuracy, not the 33% a naive median gives


def _profile_lead(lead_id: str, *, has_booking: bool, has_email: bool, has_website: bool) -> Lead:
    return Lead(
        id=lead_id, name="Biz", niche="restaurant", lat=0.0, lon=0.0,
        phone="555-0000", website="https://example.com" if has_website else "",
        emails=["a@example.com"] if has_email else [],
        has_booking=has_booking, chat_widget="", has_contact_form=None,
        site_ok=None, opening_hours="",
    )


def test_learn_keeps_rule_with_more_bad_than_good_labels(tmp_path):
    """End-to-end, with more bad labels than good. Two profiles per class so
    the base heuristic alone genuinely overlaps between classes (some
    "boosted" bad leads outscore some "dipped" good leads) -- a real gap the
    candidate rule must close, not a baseline that's already perfect. This
    is exactly the class-imbalanced shape that provokes the old median+">="
    tie bug in _threshold."""
    memory = Memory(tmp_path / "data")

    # bad, plain: score 30 (has_phone only).
    # bad, boosted (has_email): score 45 -- outscores the dipped good leads.
    # good, plain: score 50 (has_phone + no_online_booking).
    # good, dipped (no website): score 40 -- UNDER the boosted bad leads.
    profiles = (
        ("bad_plain", dict(has_booking=True, has_email=False, has_website=True), "bad", 15),
        ("bad_boosted", dict(has_booking=True, has_email=True, has_website=True), "bad", 45),
        ("good_dipped", dict(has_booking=False, has_email=False, has_website=False), "good", 20),
        ("good_plain", dict(has_booking=False, has_email=False, has_website=True), "good", 20),
    )
    i = 0
    for name, kwargs, label, count in profiles:
        for _ in range(count):
            lead = _profile_lead(f"imbal_{name}_{i}", **kwargs)
            memory.add_label(lead, label, run_id="seed_run")
            i += 1

    candidate_response = {
        "rules": [
            {"feature": "has_booking", "op": "is_false", "value": None, "weight": 20,
             "rationale": "no online booking predicts a good AI-receptionist fit"},
        ]
    }
    llm = ScriptedLLM([candidate_response])

    n_bad = sum(1 for _, _, label, count in profiles if label == "bad" for _ in range(count))
    n_good = sum(1 for _, _, label, count in profiles if label == "good" for _ in range(count))
    assert n_bad > n_good  # this test's whole premise: more bad labels than good

    report = learn(memory, llm)

    assert report.ok is True
    added_features = [(r.feature, r.op) for r in report.added]
    assert ("has_booking", "is_false") in added_features, (
        f"expected the separating rule to be kept; added={added_features} rejected={report.rejected}"
    )
    assert report.acc_after > report.acc_before


# --- HIGH: an empty/tiny select-or-test split must refuse to touch rules ---

def test_learn_refuses_when_holdout_too_small(tmp_path):
    memory = Memory(tmp_path / "data")

    # Search for >= 12 lead ids that all land in the "train" bucket (2,3,4),
    # so select and test (buckets 1 and 0) end up empty -- and even the
    # 2-way fallback (select+test combined) stays empty, well under
    # MIN_SPLIT_SIZE. This must produce a clean refusal, not touch rules,
    # and never crash trying to compute an empty-set accuracy.
    train_only_ids = []
    n = 0
    while len(train_only_ids) < 14:
        candidate_id = f"safe_lead_{n}"
        if _bucket(candidate_id) not in (0, 1):
            train_only_ids.append(candidate_id)
        n += 1

    rng = random.Random(7)
    for i, lead_id in enumerate(train_only_ids):
        lead = _make_lead(i, has_booking=(i % 2 == 0), rng=rng)
        lead.id = lead_id
        memory.add_label(lead, "good" if i % 2 else "bad", run_id="r0")

    llm = ScriptedLLM([])  # must not be called: bail before any LLM call
    rules_before = memory.load_rules()

    report = learn(memory, llm)

    assert report.ok is False
    assert "too small" in report.message.lower()
    assert llm.calls == []
    assert memory.load_rules() == rules_before  # untouched
    assert len(memory.get_history()) == 0


# --- MED: a malformed candidate rule must be rejected, not crash learn() ---

def test_parse_candidates_handles_malformed_shapes():
    response = {
        "rules": [
            {"feature": "has_phone", "op": "is_true", "value": None, "weight": 10, "rationale": "fine"},
            "not an object at all",
            {"feature": "has_phone", "op": "is_true", "value": None, "weight": "high"},
            {"feature": "has_phone", "op": "is_true", "value": None, "weight": True},
        ]
    }
    valid, rejected = _parse_candidates(response, run_id="r1")

    assert len(valid) == 1
    assert valid[0].feature == "has_phone"

    reasons = [r["reason"] for r in rejected]
    assert "not an object" in reasons
    assert reasons.count("weight not numeric") == 2  # the string "high" and the bool True


def test_parse_candidates_rules_value_not_a_list_yields_nothing():
    valid, rejected = _parse_candidates({"rules": "not a list"}, run_id="r1")
    assert valid == []
    assert rejected == []

    valid2, rejected2 = _parse_candidates("not even a dict", run_id="r1")
    assert valid2 == []
    assert rejected2 == []


def test_split3_buckets_are_disjoint_and_cover_all_labels():
    labels = [{"lead_id": f"x_{i}", "label": "good"} for i in range(30)]
    train, select, test = _split3(labels)
    assert len(train) + len(select) + len(test) == 30
    assert {r["lead_id"] for r in select} & {r["lead_id"] for r in test} == set()
    assert {r["lead_id"] for r in select} & {r["lead_id"] for r in train} == set()
