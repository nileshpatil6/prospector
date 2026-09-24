"""Learned scoring rules: a small, transparent add-on to a fixed base
heuristic. Rules only ever read from `features.py` output -- never from raw
Lead fields directly -- so every rule is auditable against a documented,
typed feature catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prospector.features import FEATURE_TYPES, features
from prospector.osm import Lead

VALID_OPS = {"==", "!=", ">=", "<=", "contains", "is_true", "is_false"}

# Which operators are legal against which declared feature type.
_OPS_FOR_TYPE: dict[type, set[str]] = {
    bool: {"==", "!=", "is_true", "is_false"},
    float: {"==", "!=", ">=", "<="},
    str: {"==", "!=", "contains"},
}

MIN_WEIGHT, MAX_WEIGHT = -30.0, 30.0
SCORE_MIN, SCORE_MAX = 0.0, 100.0


@dataclass
class Rule:
    id: str
    feature: str
    op: str
    value: bool | float | str
    weight: float
    rationale: str = ""
    created_run: str = ""
    holdout_gain: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feature": self.feature,
            "op": self.op,
            "value": self.value,
            "weight": self.weight,
            "rationale": self.rationale,
            "created_run": self.created_run,
            "holdout_gain": self.holdout_gain,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_rule(rule: Rule) -> str | None:
    """Return an error message if the rule is invalid, else None.

    Checks: the feature exists in the catalogue, the operator is legal for
    that feature's declared type, and the weight is within range.
    """
    if rule.feature not in FEATURE_TYPES:
        return f"unknown feature {rule.feature!r}"
    if rule.op not in VALID_OPS:
        return f"unknown op {rule.op!r}"
    feature_type = FEATURE_TYPES[rule.feature]
    if rule.op not in _OPS_FOR_TYPE[feature_type]:
        return f"op {rule.op!r} not valid for {feature_type.__name__} feature {rule.feature!r}"
    if not (MIN_WEIGHT <= rule.weight <= MAX_WEIGHT):
        return f"weight {rule.weight} out of range [{MIN_WEIGHT}, {MAX_WEIGHT}]"
    return None


def apply(rule: Rule, feats: dict[str, bool | float | str]) -> bool:
    """Evaluate whether `rule` matches a feature vector (as returned by
    `features()`). Unknown feature/op just fail to match rather than raise,
    since validate_rule() is the gate that should have caught it earlier."""
    if rule.feature not in feats:
        return False
    actual = feats[rule.feature]

    if rule.op == "==":
        return actual == rule.value
    if rule.op == "!=":
        return actual != rule.value
    if rule.op == "is_true":
        return bool(actual) is True
    if rule.op == "is_false":
        return bool(actual) is False
    if rule.op == "contains":
        return isinstance(actual, str) and str(rule.value) in actual
    if rule.op in (">=", "<="):
        try:
            actual_f, value_f = float(actual), float(rule.value)
        except (TypeError, ValueError):
            return False
        return actual_f >= value_f if rule.op == ">=" else actual_f <= value_f
    return False


def base_score(feats: dict[str, bool | float | str]) -> tuple[float, list[str]]:
    """The fixed, small heuristic scoring is anchored to: a business that can
    be reached by phone, takes no online bookings, and runs no chat widget is
    a good fit for an AI phone receptionist."""
    score = 0.0
    reasons: list[str] = []

    def add(points: float, label: str) -> None:
        nonlocal score
        score += points
        sign = "+" if points >= 0 else ""
        reasons.append(f"{label}: {sign}{points:g}")

    if feats["has_phone"]:
        add(30, "has_phone")
    if feats["has_email"]:
        add(15, "has_email")
    if feats["booking_known"] and not feats["has_booking"]:
        add(20, "no_online_booking")
    if not feats["has_chat_widget"]:
        add(10, "no_chat_widget")
    if feats["chat_incumbent"]:
        add(-15, "chat_incumbent")
    if feats["high_ticket_niche"]:
        add(10, "high_ticket_niche")
    if feats["hours_known"] and not feats["open_24_7"]:
        add(5, "limited_hours")
    if feats["site_ok"]:
        add(5, "site_ok")
    if not feats["has_website"]:
        add(-10, "no_website")

    return score, reasons


def score(lead: Lead, rules: list[Rule]) -> tuple[float, list[str]]:
    """Score a lead: base heuristic + sum of matching learned rules' weights,
    clamped to [0, 100]. Returns (score, reasons) where reasons lists every
    contributing base signal and rule (by id)."""
    feats = features(lead)
    total, reasons = base_score(feats)

    for rule in rules:
        if apply(rule, feats):
            sign = "+" if rule.weight >= 0 else ""
            reasons.append(f"rule:{rule.id} ({rule.rationale}): {sign}{rule.weight:g}")
            total += rule.weight

    total = max(SCORE_MIN, min(SCORE_MAX, total))
    return total, reasons
