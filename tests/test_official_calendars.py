"""Cross-check the policy engine against official observance rules published in python-holidays.

The ``us-federal`` and ``uk-england`` presets re-derive observed dates with workcal's own rules
(nearest/next workday, collision handling). If they agree with python-holidays' official observed
dates over 40 years, the rule engine is doing what the config says.
"""

import datetime as dt

import holidays
import pytest

from workcal import Policy, WorkCalendar

START, END = dt.date(2000, 1, 1), dt.date(2040, 12, 31)


def official_weekday_days_off(country: str, subdiv: str | None = None) -> set[dt.date]:
    cal = holidays.country_holidays(country, subdiv=subdiv, years=range(START.year - 1, END.year + 2), observed=True)
    return {d for d in cal if START <= d <= END and d.weekday() < 5}


def workcal_weekday_days_off(preset: str) -> set[dt.date]:
    off = WorkCalendar.from_preset(preset).days_off(START, END)
    return {d for d in off.observed if d.weekday() < 5}


@pytest.mark.parametrize(("preset", "country", "subdiv"), [("us-federal", "US", None), ("uk-england", "GB", "ENG")])
def test_matches_official_observance(preset, country, subdiv):
    ours, official = workcal_weekday_days_off(preset), official_weekday_days_off(country, subdiv)
    assert sorted(ours - official) == [] and sorted(official - ours) == []


def test_us_new_year_on_saturday_is_observed_in_previous_year():
    cal = WorkCalendar.from_preset("us-federal")
    # 2022-01-01 was a Saturday; federal employees got Friday 2021-12-31 off.
    assert not cal.is_workday(dt.date(2021, 12, 31))
    assert "New Year's Day" in set(cal.days_off(dt.date(2021, 12, 31), dt.date(2021, 12, 31)).name)


def test_uk_christmas_and_boxing_day_on_weekend_take_monday_and_tuesday():
    cal = WorkCalendar.from_preset("uk-england")
    # 2021: Christmas on Saturday, Boxing Day on Sunday -> Mon 27 and Tue 28 off.
    assert cal.workdays_between(dt.date(2021, 12, 27), dt.date(2021, 12, 28)) == 0
    assert cal.is_workday(dt.date(2021, 12, 29))


def test_nyse_closures():
    cal = WorkCalendar.from_preset("nyse")
    assert not cal.is_workday(dt.date(2026, 4, 3))  # Good Friday
    assert not cal.is_workday(dt.date(2026, 7, 3))  # Independence Day (observed)
    assert cal.is_workday(dt.date(2026, 10, 12))  # Columbus Day: markets open


def test_official_flag_uses_source_observance():
    ours = WorkCalendar.from_preset("us-federal")
    official = WorkCalendar(Policy.from_dict({"name": "t", "country": "US", "observance": {"official": True}}))
    assert workcal_weekday_days_off_for(official) == workcal_weekday_days_off_for(ours)


def workcal_weekday_days_off_for(cal: WorkCalendar) -> set[dt.date]:
    return {d for d in cal.days_off(START, END).observed if d.weekday() < 5}
