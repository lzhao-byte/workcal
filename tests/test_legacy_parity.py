"""The v2 engine, configured with the ``us-corporate-example`` preset, must reproduce v1 exactly.

v1 (tests/legacy/utils_v1.py) hard-coded one company's holiday rules and exposed five switches.
Each switch maps to a small change in the policy config, so we check all 32 combinations over
41 years, month by month.
"""

import copy
import datetime as dt
import itertools

import pytest

from tests.legacy import utils_v1
from workcal import Policy, WorkCalendar
from workcal.policy import load_policy_dict

YEARS = (2000, 2040)
SWITCHES = ["juneteenth", "good_friday", "veterans", "columbus", "shutdown"]


def v2_calendar(juneteenth, good_friday, veterans, columbus, shutdown) -> WorkCalendar:
    raw = copy.deepcopy(load_policy_dict("us-corporate-example"))
    raw["observe"] += [
        name
        for on, name in [
            (juneteenth, "Juneteenth National Independence Day"),
            (veterans, "Veterans Day"),
            (columbus, "Columbus Day"),
        ]
        if on
    ]
    if good_friday:
        raw["extra"].append({"name": "Good Friday", "date": {"easter": -2}})
    if not shutdown:
        raw.pop("shutdown")
    return WorkCalendar(Policy.from_dict(raw))


COMBOS = list(itertools.product([False, True], repeat=len(SWITCHES)))


@pytest.mark.parametrize("combo", COMBOS, ids=lambda c: "+".join(s for s, on in zip(SWITCHES, c, strict=True) if on) or "base")
def test_monthly_workdays_match_v1(combo):
    juneteenth, good_friday, veterans, columbus, shutdown = combo
    v1_holidays, v1_months = utils_v1.count_x_workdays(
        year_range=YEARS,
        include_juneteeth=juneteenth,
        include_good_friday=good_friday,
        include_veterans=veterans,
        include_columbus=columbus,
        christmas_shutdown=shutdown,
    )
    cal = v2_calendar(*combo)
    v2_months = cal.workdays_by_month(*YEARS)

    assert len(v1_months) == (YEARS[1] - YEARS[0] + 1) * 12
    assert v2_months.workdays.tolist() == v1_months.Workdays.tolist()

    v1_days = set(v1_holidays.obs_date)
    v2_days = set(cal.days_off(dt.date(YEARS[0], 1, 1), dt.date(YEARS[1], 12, 31)).observed)
    assert len(v1_days) > 300
    assert v2_days == v1_days
