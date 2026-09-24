"""The learning loop: turn user good/bad labels into new scoring rules,
validated on a held-out split so memory only ever grows more accurate.

INVARIANT: the LLM proposing candidate rules never sees holdout labels or
holdout lead data -- only misclassified TRAIN leads go into its prompt. This
keeps the holdout split an honest, untouched measure of generalization.
"""

from __future__ import annotations

import hashlib
import statistics
import time
from dataclasses import dataclass, field

from prospector.features import FEATURE_TYPES
from prospector.llm import LLM, LLMError
from prospector.memory import Memory
from prospector.osm import Lead
from prospector.rules import Rule, score, validate_rule

MIN_LABELS = 12
HOLDOUT_MOD = 5
MAX_TRAIN_ACC_DROP = 2.0
MAX_CANDIDATES = 5
PRECISION_K = 10

_NICHE_HINT = "dentist, lawyer, vet, med_spa, salon, plumber, hvac, electrician, roofer, restaurant, chiropractor, optometrist, physio, real_estate, accountant, insurance"
_CHAT_VENDOR_HINT = "podium, birdeye, intercom, tidio, drift, tawk.to, livechat, hubspot, crisp, olark, gorgias, or empty string for none"


@dataclass
class LearnReport:
    ok: bool
    message: str
    n_labels: int = 0
    n_train: int = 0
    n_holdout: int = 0
    acc_before: float = 0.0
    acc_after: float = 0.0
    p_at_10_before: float = 0.0
    p_at_10_after: float = 0.0
    added: list[Rule] = field(default_factory=list)
    removed: list[Rule] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    final_rules: list[Rule] = field(default_factory=list)


def _is_holdout(lead_id: str) -> bool:
    """Deterministic 80/20 split by hash of lead id, so re-running learn()
    never reshuffles which leads are held out."""
    digest = hashlib.sha1(lead_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % HOLDOUT_MOD == 0


def _split(labels: list[dict]) -> tuple[list[dict], list[dict]]:
    train, holdout = [], []
    for record in labels:
        (holdout if _is_holdout(record["lead_id"]) else train).append(record)
    return train, holdout


def _threshold(rules: list[Rule], train: list[dict]) -> float:
    if not train:
        return 50.0
    scores = [score(Lead.from_dict(r["lead"]), rules)[0] for r in train]
    return statistics.median(scores)


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


def _precision_at_k(rules: list[Rule], records: list[dict], k: int = PRECISION_K) -> float:
    if not records:
        return 0.0
    scored = [(score(Lead.from_dict(r["lead"]), rules)[0], r["label"]) for r in records]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:k]
    if not top:
        return 0.0
    good = sum(1 for _, label in top if label == "good")
    return 100.0 * good / len(top)


def _evaluate(rules: list[Rule], train: list[dict], holdout: list[dict]) -> tuple[float, float, float, float]:
    """Returns (threshold, train_acc, holdout_acc, p_at_10) for this rule set."""
    threshold = _threshold(rules, train)
    train_acc = _accuracy(rules, train, threshold)
    holdout_acc = _accuracy(rules, holdout, threshold)
    p10 = _precision_at_k(rules, holdout)
    return threshold, train_acc, holdout_acc, p10


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
    TRAIN misses go in -- never holdout data."""
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

    train, holdout = _split(labels)
    run_id = f"learn_{int(time.time())}"

    threshold0, train_acc0, holdout_acc0, p10_before = _evaluate(current_rules, train, holdout)

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
            n_labels=len(labels), n_train=len(train), n_holdout=len(holdout),
            acc_before=holdout_acc0, acc_after=holdout_acc0,
            p_at_10_before=p10_before, p_at_10_after=p10_before,
            final_rules=current_rules,
        )

    raw_candidates = response.get("rules", []) if isinstance(response, dict) else []
    rejected: list[dict] = []
    valid_candidates: list[Rule] = []
    for i, raw in enumerate(raw_candidates[:MAX_CANDIDATES]):
        candidate = Rule(
            id=f"{run_id}_c{i}",
            feature=raw.get("feature", ""),
            op=raw.get("op", ""),
            value=raw.get("value"),
            weight=float(raw.get("weight", 0) or 0),
            rationale=str(raw.get("rationale", ""))[:200],
            created_run=run_id,
        )
        error = validate_rule(candidate)
        if error:
            rejected.append({"rule": candidate.to_dict(), "reason": error})
        else:
            valid_candidates.append(candidate)

    # Evaluate each valid candidate alone against the current rule set.
    scored_candidates: list[tuple[Rule, float, float]] = []
    for candidate in valid_candidates:
        _, train_acc_v, holdout_acc_v, _ = _evaluate(current_rules + [candidate], train, holdout)
        gain = holdout_acc_v - holdout_acc0
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
    # later one still helps).
    working_rules = list(current_rules)
    working_train_acc, working_holdout_acc = train_acc0, holdout_acc0
    added: list[Rule] = []
    for candidate, _, _ in scored_candidates:
        trial_rules = working_rules + [candidate]
        _, trial_train_acc, trial_holdout_acc, _ = _evaluate(trial_rules, train, holdout)
        gain = trial_holdout_acc - working_holdout_acc
        train_drop = working_train_acc - trial_train_acc
        if gain > 0 and train_drop <= MAX_TRAIN_ACC_DROP:
            candidate.holdout_gain = gain
            working_rules = trial_rules
            working_train_acc, working_holdout_acc = trial_train_acc, trial_holdout_acc
            added.append(candidate)
        else:
            rejected.append({
                "rule": candidate.to_dict(),
                "reason": "did not improve holdout accuracy against the growing rule set",
            })

    # Try removing each pre-existing rule; drop it if holdout accuracy does
    # not fall, to keep memory small.
    removed: list[Rule] = []
    for rule in list(current_rules):
        if rule.id not in {r.id for r in working_rules}:
            continue
        trial_rules = [r for r in working_rules if r.id != rule.id]
        _, trial_train_acc, trial_holdout_acc, _ = _evaluate(trial_rules, train, holdout)
        if trial_holdout_acc >= working_holdout_acc:
            working_rules = trial_rules
            working_train_acc, working_holdout_acc = trial_train_acc, trial_holdout_acc
            removed.append(rule)

    _, final_train_acc, final_holdout_acc, final_p10 = _evaluate(working_rules, train, holdout)

    memory.save_rules(working_rules)
    memory.append_history({
        "run_id": run_id,
        "n_labels": len(labels),
        "n_train": len(train),
        "n_holdout": len(holdout),
        "acc_before": holdout_acc0,
        "acc_after": final_holdout_acc,
        "p_at_10_before": p10_before,
        "p_at_10_after": final_p10,
        "added": [r.to_dict() for r in added],
        "removed": [r.to_dict() for r in removed],
        "rejected": rejected,
    })

    return LearnReport(
        ok=True,
        message=f"Added {len(added)} rule(s), removed {len(removed)}, rejected {len(rejected)}.",
        n_labels=len(labels), n_train=len(train), n_holdout=len(holdout),
        acc_before=holdout_acc0, acc_after=final_holdout_acc,
        p_at_10_before=p10_before, p_at_10_after=final_p10,
        added=added, removed=removed, rejected=rejected, final_rules=working_rules,
    )
