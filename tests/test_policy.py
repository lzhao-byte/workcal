import datetime as dt

import pytest

from workcal import Policy, PolicyError, WorkCalendar, list_presets, load_policy
from workcal.policy import names_match


def cal(**overrides) -> WorkCalendar:
    raw = {"name": "test", "country": "US", "observe": ["Independence Day"], **overrides}
    return WorkCalendar(Policy.from_dict(raw))


# ---------------------------------------------------------------- observance rules
# Independence Day: 2026-07-04 is a Saturday, 2027-07-04 is a Sunday.
@pytest.mark.parametrize(
    ("rule", "sat_observed", "sun_observed"),
    [
        ("nearest_workday", dt.date(2026, 7, 3), dt.date(2027, 7, 5)),
        ("previous_workday", dt.date(2026, 7, 3), dt.date(2027, 7, 2)),
        ("next_workday", dt.date(2026, 7, 6), dt.date(2027, 7, 5)),
        ("none", dt.date(2026, 7, 4), dt.date(2027, 7, 4)),
    ],
)
def test_weekend_shift_rules(rule, sat_observed, sun_observed):
    c = cal(observance={"default": rule})
    observed = set(c.days_off(dt.date(2026, 1, 1), dt.date(2027, 12, 31)).observed)
    assert observed == {sat_observed, sun_observed}


def test_rule_none_means_weekend_holiday_costs_no_workday():
    assert cal(observance={"default": "none"}).workdays_between(dt.date(2026, 6, 29), dt.date(2026, 7, 10)) == 10


def test_per_holiday_override_beats_default():
    c = cal(observe=["Independence Day", "Christmas Day"], observance={"default": "none", "overrides": {"Christmas Day": "next_workday"}})
    off = c.days_off(dt.date(2027, 1, 1), dt.date(2027, 12, 31))
    assert dict(zip(off.name, off.observed, strict=True)) == {
        "Independence Day": dt.date(2027, 7, 4),  # Sunday, rule none
        "Christmas Day": dt.date(2027, 12, 27),  # Saturday -> Monday
    }


def test_custom_weekend_friday_saturday():
    # 2026-07-03 is a Friday: with a Fri/Sat weekend, the nearest workday is Thursday.
    c = WorkCalendar(
        Policy.from_dict(
            {
                "name": "t",
                "country": "US",
                "observe": [],
                "weekend": ["fri", "sat"],
                "extra": [{"name": "Company Day", "date": {"month": 7, "day": 3}}],
            }
        )
    )
    assert set(c.days_off(dt.date(2026, 7, 1), dt.date(2026, 7, 31)).observed) == {dt.date(2026, 7, 2)}
    assert c.is_workday(dt.date(2026, 7, 5))  # Sunday is a workday
    assert not c.is_workday(dt.date(2026, 7, 4))  # Saturday is not


def test_collision_pushes_to_next_free_workday():
    # Two company days on the same Saturday: nearest workday is Friday for both -> second one moves to Monday.
    extras = [{"name": "A", "date": {"month": 7, "day": 4}}, {"name": "B", "date": {"month": 7, "day": 4}}]
    keep = WorkCalendar(Policy.from_dict({"name": "t", "country": "US", "observe": [], "extra": extras}))
    push = WorkCalendar(
        Policy.from_dict({"name": "t", "country": "US", "observe": [], "extra": extras, "observance": {"on_collision": "next_workday"}})
    )
    span = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
    assert set(keep.days_off(*span).observed) == {dt.date(2026, 7, 3)}
    assert set(push.days_off(*span).observed) == {dt.date(2026, 7, 3), dt.date(2026, 7, 6)}


# ---------------------------------------------------------------- extras and shutdowns
def test_easter_offset_gives_good_friday():
    c = cal(observe=[], extra=[{"name": "Good Friday", "date": {"easter": -2}}])
    assert c.days_off(dt.date(2026, 1, 1), dt.date(2026, 12, 31)).observed.tolist() == [dt.date(2026, 4, 3)]


def test_relative_extra_uses_actual_holiday_date():
    c = cal(observe=["Thanksgiving"], extra=[{"name": "Black Friday", "date": {"holiday": "Thanksgiving", "offset_days": 1}}])
    assert dt.date(2026, 11, 27) in set(c.days_off(dt.date(2026, 11, 1), dt.date(2026, 11, 30)).observed)


def test_shutdown_covers_every_day_and_replaces_holidays():
    c = cal(
        observe=["Christmas Day"],
        shutdown=[
            {"name": "Winter break", "start": {"month": 12, "day": 22}, "end": {"month": 12, "day": 31}, "replaces": ["Christmas Day"]}
        ],
    )
    off = c.days_off(dt.date(2026, 12, 1), dt.date(2026, 12, 31))
    assert set(off.name) == {"Winter break"}
    assert len(off) == 10
    assert c.workdays_between(dt.date(2026, 12, 21), dt.date(2026, 12, 31)) == 1  # only Mon 21


def test_shutdown_ending_before_start_is_rejected():
    c = cal(shutdown=[{"name": "x", "start": {"month": 12, "day": 31}, "end": {"month": 12, "day": 1}}])
    with pytest.raises(PolicyError, match="ends before it starts"):
        c.days_off(dt.date(2026, 1, 1), dt.date(2026, 12, 31))


# ---------------------------------------------------------------- validation
def test_holiday_names_survive_upstream_renames():
    # python-holidays renamed "Thanksgiving" to "Thanksgiving Day"; both spellings must work.
    assert names_match("Thanksgiving", "Thanksgiving Day")
    assert names_match("Christmas Day (observed)", "christmas day")
    assert not names_match("Christmas Day", "Christmas Eve")
    assert not names_match("New Year's Day", "New Year's Eve")
    for spelling in ["Thanksgiving", "Thanksgiving Day"]:
        assert len(cal(observe=[spelling]).days_off(dt.date(2026, 11, 1), dt.date(2026, 11, 30))) == 1


def test_typo_in_holiday_name_fails_with_suggestion():
    with pytest.raises(PolicyError, match="did you mean"):
        cal(observe=["Independance Day"])


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"name": "x"}, "exactly one of 'country'"),
        ({"name": "x", "country": "US", "market": "NYSE"}, "exactly one of 'country'"),
        ({"name": "x", "country": "US", "weekend": ["sat", "funday"]}, "weekend days"),
        ({"name": "x", "country": "US", "weekend": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}, "whole week"),
        ({"name": "x", "country": "US", "observance": {"default": "sometimes"}}, "observance rule"),
        ({"name": "x", "country": "US", "observance": {"on_collision": "shrug"}}, "on_collision"),
        ({"name": "x", "country": "US", "extra": [{"name": "y", "date": {"month": 13, "day": 1}}]}, "invalid month/day"),
        ({"name": "x", "country": "US", "extra": [{"name": "y", "date": {"month": 1, "day": 1, "easter": 0}}]}, "exactly one of"),
        ({"name": "x", "country": "US", "surprise": 1}, "unknown top-level keys"),
        ({"country": "US"}, "needs a name"),
    ],
)
def test_invalid_policies_are_rejected(raw, message):
    with pytest.raises(PolicyError, match=message):
        Policy.from_dict(raw)


def test_all_presets_load_and_build():
    assert set(list_presets()) >= {"us-federal", "us-corporate-example", "uk-england", "nyse"}
    for name in list_presets():
        c = WorkCalendar(load_policy(name))
        assert 240 <= c.workdays_between(dt.date(2026, 1, 1), dt.date(2026, 12, 31)) <= 256


def test_unknown_preset():
    with pytest.raises(PolicyError, match="no preset"):
        load_policy("atlantis")
