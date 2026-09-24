"""The learning loop: turn user good/bad labels into new scoring rules,
validated on data the rule-selection step never touches.

INVARIANT: the LLM proposing candidate rules never sees select/test labels or
lead data -- only misclassified TRAIN leads go into its prompt.

Labels are split three ways by sha1(lead_id) % 5: bucket 0 = test (final
reporting only), bucket 1 = select (used to decide which candidate rules to
keep/drop), everything else = train (used to pick the score threshold and to
find misclassified leads for the LLM prompt). Choosing rules on `select` and
reporting accuracy on `test` keeps the reported numbers honest: a rule set
that overfits the selection data won't automatically look good on the test
split too. When there isn't enough data for a clean 3-way split, this falls
back to a 2-way split (select and test share the same records) and says so
explicitly in the history entry -- that fallback is optimistic and the
README says as much.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from prospector.features import FEATURE_TYPES
from prospector.llm import LLM, LLMError
from prospector.memory import Memory
from prospector.osm import Lead
from prospector.rules import Rule, score, validate_rule

MIN_LABELS = 12
SPLIT_MOD = 5
MIN_SPLIT_SIZE = 3  # fewer than this, or single-class, can't validate rules safely
STRICT_REMOVAL_BELOW = 10  # select set smaller than this requires strictly positive gain to remove a rule
MAX_TRAIN_ACC_DROP = 2.0
MAX_CANDIDATES = 5
PRECISION_K = 10
MIN_TEST_FOR_PRECISION = 4
FALLBACK_NOTE = "optimistic: selection and test share data"

_NICHE_HINT = "dentist, lawyer, vet, med_spa, salon, plumber, hvac, electrician, roofer, restaurant, chiropractor, optometrist, physio, real_estate, accountant, insurance"
_CHAT_VENDOR_HINT = "podium, birdeye, intercom, tidio, drift, tawk.to, livechat, hubspot, crisp, olark, gorgias, or empty string for none"


@dataclass
class LearnReport:
    ok: bool
    message: str
    n_labels: int = 0
    n_train: int = 0
    n_holdout: int = 0  # size of the `select` set used to validate rule changes
    acc_before: float = 0.0
    acc_after: float = 0.0
    p_at_10_before: float | None = 0.0
    p_at_10_after: float | None = 0.0
    added: list[Rule] = field(default_factory=list)
    removed: list[Rule] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    final_rules: list[Rule] = field(default_factory=list)


def _bucket(lead_id: str) -> int:
    """Deterministic 0-4 bucket by hash of lead id, so re-running learn()
    never reshuffles which leads land where."""
    digest = hashlib.sha1(lead_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % SPLIT_MOD


def _split3(labels: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split into (train, select, test) by bucket: 0 -> test, 1 -> select,
    everything else -> train (roughly 60/20/20)."""
    train, select, test = [], [], []
    for record in labels:
        bucket = _bucket(record["lead_id"])
        if bucket == 0:
            test.append(record)
        elif bucket == 1:
            select.append(record)
        else:
            train.append(record)
    return train, select, test


def _is_valid_eval_set(records: list[dict]) -> bool:
    if len(records) < MIN_SPLIT_SIZE:
        return False
    return len({r["label"] for r in records}) >= 2


def _threshold(rules: list[Rule], train: list[dict]) -> float:
    """The score threshold (predict "good" iff score >= threshold) that
    maximizes TRAIN accuracy, searched over every midpoint between
    neighbouring distinct train scores (plus one point below the minimum,
    so an all-good or all-bad train set is still reachable). Ties in
    accuracy break toward the LOWER threshold, which is what iterating
    candidates in ascending order and only updating on a STRICT
    improvement gives for free.

    This replaces a plain median: with ">=" tie-breaking, the median of a
    class-imbalanced score list can land exactly ON a cluster of tied
    scores and push all of them to the wrong side, rejecting a rule that
    actually separates the classes perfectly.
    """
    if not train:
        return 50.0
    scored = [(score(Lead.from_dict(r["lead"]), rules)[0], r["label"]) for r in train]
    distinct = sorted({s for s, _ in scored})

    candidates = [distinct[0] - 1.0]
    candidates.extend((a + b) / 2.0 for a, b in zip(distinct, distinct[1:]))

    best_threshold = candidates[0]
    best_acc = -1.0
    for cand in candidates:  # ascending order
        correct = sum(1 for s, label in scored if (("good" if s >= cand else "bad") == label))
        acc = correct / len(scored)
        if acc > best_acc:  # strict: first (lowest) candidate wins ties
            best_acc = acc
            best_threshold = cand
    return best_threshold


def _accuracy(rules: list[Rule], records: list[dict], threshold: float) -> float:
    if not records:
        return 0.0
    correct = 0
    for record in records:
        lead = Lead.from_dict(record["lead"])
        predicted = "good" if score(lead, rules)[0] >= threshold else "bad"
        if predicted == record["label"]:
            correct += 1
    return 100.0 * correct / len(records)


def _precision_at_k(rules: list[Rule], records: list[dict], k: int) -> float:
    if not records or k <= 0:
        return 0.0
    scored = [(score(Lead.from_dict(r["lead"]), rules)[0], r["label"]) for r in records]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:k]
    if not top:
        return 0.0
    good = sum(1 for _, label in top if label == "good")
    return 100.0 * good / len(top)


def _evaluate(rules: list[Rule], train: list[dict], eval_records: list[dict]) -> tuple[float, float, float]:
    """Returns (threshold, train_acc, eval_acc). The threshold always comes
    from TRAIN ONLY, then is applied to both sets -- eval_records never
    influences where the boundary is drawn."""
    threshold = _threshold(rules, train)
    train_acc = _accuracy(rules, train, threshold)
    eval_acc = _accuracy(rules, eval_records, threshold)
    return threshold, train_acc, eval_acc


def _allowed_values(feature: str) -> str:
    ftype = FEATURE_TYPES.get(feature)
    if ftype is bool:
        return "true/false"
    if ftype is float:
        return "a non-negative number"
    if feature == "niche":
        return _NICHE_HINT
    if feature == "chat_vendor":
        return _CHAT_VENDOR_HINT
    return "any string"


def _feature_catalogue() -> str:
    lines = []
    for name, ftype in sorted(FEATURE_TYPES.items()):
        lines.append(f"- {name} ({ftype.__name__}): allowed values = {_allowed_values(name)}")
    return "\n".join(lines)


def _build_prompt(misses: list[dict], current_rules: list[Rule]) -> tuple[str, str, str]:
    """Build the (system, user, schema_hint) for the one LLM call. Only
    TRAIN misses go in -- never select/test data."""
    system = (
        "You are tuning a lead-scoring rule set for an AI phone receptionist "
        "sales tool. You will be shown leads the current rules mis-scored and "
        "the feature catalogue they may reference. Propose small, targeted "
        "rule changes."
    )

    miss_lines = []
    for record in misses:
        feats = record["features"]
        miss_lines.append(
            f"- lead_id={record['lead_id']} true_label={record['label']} features={feats}"
        )
    misses_block = "\n".join(miss_lines) if miss_lines else "(no misclassified training leads)"

    rules_block = "\n".join(
        f"- {r.id}: {r.feature} {r.op} {r.value!r} weight={r.weight} ({r.rationale})"
        for r in current_rules
    ) or "(no rules yet)"

    user = (
        f"Misclassified training leads:\n{misses_block}\n\n"
        f"Current rules:\n{rules_block}\n\n"
        f"Feature catalogue:\n{_feature_catalogue()}\n\n"
        "Propose up to 5 candidate rules that would fix some of these misses "
        "without contradicting the rest. Each rule's `feature` must be one of "
        "the catalogue names, `op` one of ==, !=, >=, <=, contains, is_true, "
        "is_false (matching the feature's type), `weight` between -30 and 30."
    )

    schema_hint = (
        '{"rules": [{"feature": "<name>", "op": "<op>", "value": <bool|number|string>, '
        '"weight": <-30..30>, "rationale": "<short reason>"}]}'
    )
    return system, user, schema_hint


def _parse_candidates(raw_response: object, run_id: str) -> tuple[list[Rule], list[dict]]:
    """Turn the LLM's raw response into validated Rule candidates. Never
    raises: a malformed item is rejected with a reason instead of crashing
    the whole learning run."""
    raw_rules = raw_response.get("rules", []) if isinstance(raw_response, dict) else []
    if not isinstance(raw_rules, list):
        raw_rules = []

    rejected: list[dict] = []
    valid: list[Rule] = []
    for i, raw in enumerate(raw_rules[:MAX_CANDIDATES]):
        if not isinstance(raw, dict):
            rejected.append({"rule": {"raw": raw}, "reason": "not an object"})
            continue

        weight_raw = raw.get("weight", 0)
        if not isinstance(weight_raw, (int, float)) or isinstance(weight_raw, bool):
            rejected.append({"rule": raw, "reason": "weight not numeric"})
            continue

        candidate = Rule(
            id=f"{run_id}_c{i}",
            feature=raw.get("feature", ""),
            op=raw.get("op", ""),
            value=raw.get("value"),
            weight=float(weight_raw),
            rationale=str(raw.get("rationale", ""))[:200],
            created_run=run_id,
        )
        error = validate_rule(candidate)
        if error:
            rejected.append({"rule": candidate.to_dict(), "reason": error})
        else:
            valid.append(candidate)
    return valid, rejected


def learn(memory: Memory, llm: LLM) -> LearnReport:
    labels = memory.get_labels()
    current_rules = memory.load_rules()

    n_good = sum(1 for r in labels if r["label"] == "good")
    n_bad = sum(1 for r in labels if r["label"] == "bad")
    if len(labels) < MIN_LABELS or n_good == 0 or n_bad == 0:
        return LearnReport(
            ok=False,
            message=(
                f"Need at least {MIN_LABELS} labels with both good and bad present "
                f"(have {len(labels)} labels: {n_good} good, {n_bad} bad). No learning run."
            ),
            n_labels=len(labels),
            final_rules=current_rules,
        )

    train, select, test = _split3(labels)

    fallback_note: str | None = None
    if not _is_valid_eval_set(select) or not _is_valid_eval_set(test):
        # Not enough data for a clean 3-way split: fall back to select and
        # test sharing the same records. This is explicitly optimistic
        # (the same data picks rules and grades them) and gets logged as such.
        combined = select + test
        select, test = combined, combined
        fallback_note = FALLBACK_NOTE

    if not _is_valid_eval_set(select):
        # Still too small even combined -- refuse to touch memory rather
        # than validate rule changes against noise.
        classes = {r["label"] for r in select}
        return LearnReport(
            ok=False,
            message=(
                f"Holdout too small to validate rules safely (have {len(select)} "
                f"labels, {len(classes)} class(es)). No learning run."
            ),
            n_labels=len(labels), n_train=len(train), n_holdout=len(select),
            final_rules=current_rules,
        )

    run_id = f"learn_{int(time.time())}"

    threshold0, train_acc0, select_acc0 = _evaluate(current_rules, train, select)
    _, _, test_acc0 = _evaluate(current_rules, train, test)

    n_test = len(test)
    k = min(PRECISION_K, n_test // 2)
    p10_before = _precision_at_k(current_rules, test, k) if n_test >= MIN_TEST_FOR_PRECISION else None

    misses = [
        r for r in train
        if (("good" if score(Lead.from_dict(r["lead"]), current_rules)[0] >= threshold0 else "bad") != r["label"])
    ]

    system, user, schema_hint = _build_prompt(misses, current_rules)
    try:
        response = llm.json(system, user, schema_hint)
    except LLMError as exc:
        return LearnReport(
            ok=False,
            message=f"LLM call failed: {exc}",
            n_labels=len(labels), n_train=len(train), n_holdout=len(select),
            acc_before=test_acc0, acc_after=test_acc0,
            p_at_10_before=p10_before, p_at_10_after=p10_before,
            final_rules=current_rules,
        )

    valid_candidates, rejected = _parse_candidates(response, run_id)

    # Evaluate each valid candidate alone against the current rule set, on select.
    scored_candidates: list[tuple[Rule, float, float]] = []
    for candidate in valid_candidates:
        _, train_acc_v, select_acc_v = _evaluate(current_rules + [candidate], train, select)
        gain = select_acc_v - select_acc0
        train_drop = train_acc0 - train_acc_v
        if gain > 0 and train_drop <= MAX_TRAIN_ACC_DROP:
            scored_candidates.append((candidate, gain, train_acc_v - train_acc0))
        else:
            reason = (
                f"holdout accuracy gain {gain:.2f} <= 0"
                if gain <= 0
                else f"train accuracy dropped {train_drop:.2f} points (> {MAX_TRAIN_ACC_DROP} allowed)"
            )
            rejected.append({"rule": candidate.to_dict(), "reason": reason})

    scored_candidates.sort(key=lambda t: (t[1], t[2]), reverse=True)

    # Greedy addition: add kept candidates one at a time, re-checking gain
    # against the growing rule set (an earlier addition can change whether a
    # later one still helps), always measured on select.
    working_rules = list(current_rules)
    working_train_acc, working_select_acc = train_acc0, select_acc0
    added: list[Rule] = []
    for candidate, _, _ in scored_candidates:
        trial_rules = working_rules + [candidate]
        _, trial_train_acc, trial_select_acc = _evaluate(trial_rules, train, select)
        gain = trial_select_acc - working_select_acc
        train_drop = working_train_acc - trial_train_acc
        if gain > 0 and train_drop <= MAX_TRAIN_ACC_DROP:
            candidate.holdout_gain = gain
            working_rules = trial_rules
            working_train_acc, working_select_acc = trial_train_acc, trial_select_acc
            added.append(candidate)
        else:
            rejected.append({
                "rule": candidate.to_dict(),
                "reason": "did not improve holdout accuracy against the growing rule set",
            })

    # Try removing each pre-existing rule; drop it if select accuracy does
    # not fall, to keep memory small. With a small select set (< 10 labels)
    # a tie is not trustworthy enough to act on -- require a strict gain.
    require_strict_removal = len(select) < STRICT_REMOVAL_BELOW
    removed: list[Rule] = []
    for rule in list(current_rules):
        if rule.id not in {r.id for r in working_rules}:
            continue
        trial_rules = [r for r in working_rules if r.id != rule.id]
        _, trial_train_acc, trial_select_acc = _evaluate(trial_rules, train, select)
        keep_removed = (
            trial_select_acc > working_select_acc
            if require_strict_removal
            else trial_select_acc >= working_select_acc
        )
        if keep_removed:
            working_rules = trial_rules
            working_train_acc, working_select_acc = trial_train_acc, trial_select_acc
            removed.append(rule)

    _, final_train_acc, final_test_acc = _evaluate(working_rules, train, test)
    p10_after = _precision_at_k(working_rules, test, k) if n_test >= MIN_TEST_FOR_PRECISION else None

    memory.save_rules(working_rules)
    history_record = {
        "run_id": run_id,
        "n_labels": len(labels),
        "n_train": len(train),
        "n_select": len(select),
        "n_test": len(test),
        "acc_before": test_acc0,
        "acc_after": final_test_acc,
        "p_at_10_before": p10_before,
        "p_at_10_after": p10_after,
        "added": [r.to_dict() for r in added],
        "removed": [r.to_dict() for r in removed],
        "rejected": rejected,
    }
    if fallback_note:
        history_record["note"] = fallback_note
    memory.append_history(history_record)

    message = f"Added {len(added)} rule(s), removed {len(removed)}, rejected {len(rejected)}."
    if fallback_note:
        message += f" ({fallback_note})"

    return LearnReport(
        ok=True,
        message=message,
        n_labels=len(labels), n_train=len(train), n_holdout=len(select),
        acc_before=test_acc0, acc_after=final_test_acc,
        p_at_10_before=p10_before, p_at_10_after=p10_after,
        added=added, removed=removed, rejected=rejected, final_rules=working_rules,
    )
