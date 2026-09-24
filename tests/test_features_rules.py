from prospector.features import features
from prospector.osm import Lead
from prospector.rules import Rule, apply, score, validate_rule


def _lead(**overrides) -> Lead:
    base = dict(
        id="osm:node/1", name="Test Biz", niche="dentist", lat=0.0, lon=0.0,
        phone="555-1234", website="https://example.com", emails=["a@example.com"],
        has_booking=False, chat_widget="", has_contact_form=True, site_ok=True,
        opening_hours="Mo-Fr 09:00-18:00",
    )
    base.update(overrides)
    return Lead(**base)


def test_features_basic_bools_and_derived_fields():
    feats = features(_lead())
    assert feats["has_website"] is True
    assert feats["has_phone"] is True
    assert feats["has_email"] is True
    assert feats["email_count"] == 1.0
    assert feats["has_booking"] is False
    assert feats["booking_known"] is True
    assert feats["has_chat_widget"] is False
    assert feats["hours_known"] is True
    assert feats["open_24_7"] is False
    assert feats["niche"] == "dentist"
    assert feats["high_ticket_niche"] is True


def test_features_unknown_booking_state():
    feats = features(_lead(has_booking=None))
    assert feats["booking_known"] is False
    assert feats["has_booking"] is False  # bool(None) is False, but booking_known distinguishes it


def test_features_chat_incumbent():
    feats = features(_lead(chat_widget="Podium"))
    assert feats["chat_incumbent"] is True
    assert feats["chat_vendor"] == "Podium"


def test_features_24_7_and_weekends():
    feats = features(_lead(opening_hours="24/7"))
    assert feats["open_24_7"] is True
    assert feats["open_weekends"] is True


def test_features_open_weekends_true_when_weekend_hours_given():
    feats = features(_lead(opening_hours="Mo-Fr 09:00-18:00; Sa 10:00-14:00"))
    assert feats["open_weekends"] is True


def test_features_open_weekends_false_when_explicitly_off():
    # MED regression: "Su off" and "Sa,Su off" contain the day token "su"/"sa"
    # as a substring, but explicitly mean NOT open that day.
    feats = features(_lead(opening_hours="Mo-Fr 09:00-18:00; Su off"))
    assert feats["open_weekends"] is False

    feats2 = features(_lead(opening_hours="Mo-Fr 09:00-18:00; Sa,Su off"))
    assert feats2["open_weekends"] is False


def test_features_chat_known_requires_confirmed_site_ok():
    # site_ok True: the page was actually fetched, so absence of a chat
    # widget is a confirmed observation.
    assert features(_lead(site_ok=True))["chat_known"] is True
    # site_ok False or None (never fetched / fetch failed): unknown, not "no".
    assert features(_lead(site_ok=False))["chat_known"] is False
    assert features(_lead(site_ok=None))["chat_known"] is False


def test_apply_all_operators():
    feats = {"has_phone": True, "email_count": 3.0, "niche": "dentist"}
    assert apply(Rule("r1", "has_phone", "is_true", None, 1), feats) is True
    assert apply(Rule("r2", "has_phone", "is_false", None, 1), feats) is False
    assert apply(Rule("r3", "email_count", ">=", 2, 1), feats) is True
    assert apply(Rule("r4", "email_count", "<=", 2, 1), feats) is False
    assert apply(Rule("r5", "niche", "==", "dentist", 1), feats) is True
    assert apply(Rule("r6", "niche", "!=", "dentist", 1), feats) is False
    assert apply(Rule("r7", "niche", "contains", "dent", 1), feats) is True


def test_apply_unknown_feature_does_not_match():
    assert apply(Rule("r1", "nonexistent", "is_true", None, 1), {"has_phone": True}) is False


def test_validate_rule_catches_unknown_feature():
    err = validate_rule(Rule("r1", "nonexistent_feature", "is_true", None, 5))
    assert err is not None and "unknown feature" in err


def test_validate_rule_catches_wrong_op_for_type():
    # "contains" is only valid for str features, not bool.
    err = validate_rule(Rule("r1", "has_phone", "contains", "x", 5))
    assert err is not None and "not valid for" in err


def test_validate_rule_catches_out_of_range_weight():
    err = validate_rule(Rule("r1", "has_phone", "is_true", None, 999))
    assert err is not None and "out of range" in err


def test_validate_rule_accepts_valid_rule():
    err = validate_rule(Rule("r1", "has_phone", "is_true", None, 10))
    assert err is None


def test_base_score_no_chat_widget_bonus_requires_chat_known():
    # HIGH regression: a lead that was never enriched (site_ok is None, so
    # chat_widget is still "") must NOT get credit for "no chat widget" --
    # that absence was never actually confirmed.
    never_enriched = _lead(site_ok=None, chat_widget="", fetch_error="")
    s_unknown, reasons_unknown = score(never_enriched, [])
    assert not any("no_chat_widget" in r for r in reasons_unknown)

    # A lead that WAS successfully fetched (site_ok True) and genuinely has
    # no chat widget gets the bonus.
    confirmed_no_chat = _lead(site_ok=True, chat_widget="")
    s_confirmed, reasons_confirmed = score(confirmed_no_chat, [])
    assert any("no_chat_widget" in r for r in reasons_confirmed)
    assert s_confirmed > s_unknown


def test_score_clamps_to_0_100():
    # Stack many high-weight matching rules to try to blow past 100.
    rules = [Rule(f"r{i}", "has_phone", "is_true", None, 30) for i in range(10)]
    s, reasons = score(_lead(), rules)
    assert s == 100.0

    rules_negative = [Rule(f"n{i}", "has_phone", "is_true", None, -30) for i in range(10)]
    s2, _ = score(_lead(), rules_negative)
    assert s2 == 0.0


def test_score_reasons_list_includes_base_and_rules():
    rule = Rule("bonus", "has_email", "is_true", None, 12, rationale="emails convert better")
    s, reasons = score(_lead(), [rule])
    assert any("has_phone" in r for r in reasons)
    assert any("rule:bonus" in r for r in reasons)
    assert s > 0


def test_score_rule_that_does_not_match_is_absent_from_reasons():
    rule = Rule("nomatch", "has_chat_widget", "is_true", None, 12)
    _, reasons = score(_lead(), [rule])  # lead has no chat widget
    assert not any("rule:nomatch" in r for r in reasons)
