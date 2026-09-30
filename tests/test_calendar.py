import datetime as dt

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from workcal import WorkCalendar

FED = WorkCalendar.from_preset("us-federal")
CORP = WorkCalendar.from_preset("us-corporate-example")


# ---------------------------------------------------------------- counting
def test_workdays_between_is_inclusive():
    friday = dt.date(2026, 1, 9)
    assert FED.workdays_between(friday, friday) == 1
    assert FED.workdays_between(friday, friday + dt.timedelta(days=3)) == 2  # Fri + Mon
    assert FED.workdays_between(dt.date(2026, 1, 1), dt.date(2026, 1, 31)) == 20  # 22 weekdays - New Year - MLK


def test_workdays_between_rejects_reversed_range():
    with pytest.raises(ValueError):
        FED.workdays_between(dt.date(2026, 2, 1), dt.date(2026, 1, 1))


def test_is_workday():
    assert not FED.is_workday(dt.date(2026, 7, 3))  # Independence Day observed
    assert not FED.is_workday(dt.date(2026, 7, 4))  # Saturday
    assert FED.is_workday(dt.date(2026, 7, 6))


# ---------------------------------------------------------------- WORKDAY()-style arithmetic
@pytest.mark.parametrize(
    ("start", "n", "expected"),
    [
        (dt.date(2026, 1, 9), 1, dt.date(2026, 1, 12)),  # Fri + 1 -> Mon
        (dt.date(2026, 1, 10), 1, dt.date(2026, 1, 12)),  # Sat + 1 -> Mon
        (dt.date(2026, 1, 12), -1, dt.date(2026, 1, 9)),  # Mon - 1 -> Fri
        (dt.date(2026, 1, 10), -1, dt.date(2026, 1, 9)),  # Sat - 1 -> Fri
        (dt.date(2026, 1, 16), 1, dt.date(2026, 1, 20)),  # Fri + 1 skips MLK Day
        (dt.date(2026, 1, 10), 0, dt.date(2026, 1, 10)),  # 0 returns the date unchanged
        (dt.date(2026, 11, 25), 1, dt.date(2026, 11, 30)),  # corporate: skips Thanksgiving + Friday
    ],
)
def test_add_workdays(start, n, expected):
    cal = CORP if start.month == 11 else FED
    assert cal.add_workdays(start, n) == expected


@settings(max_examples=200, deadline=None)
@given(start=st.dates(dt.date(2000, 1, 1), dt.date(2040, 12, 31)), n=st.integers(-400, 400).filter(bool))
def test_add_workdays_round_trips_with_count(start, n):
    end = CORP.add_workdays(start, n)
    assert CORP.is_workday(end)
    if n > 0:
        assert CORP.workdays_between(start + dt.timedelta(days=1), end) == n
    else:
        assert CORP.workdays_between(end, start - dt.timedelta(days=1)) == -n


# ---------------------------------------------------------------- monthly summary
def test_workdays_by_month_breakdown_adds_up():
    m = CORP.workdays_by_month(2025, 2027)
    assert len(m) == 36
    assert (m.calendar_days == m.weekend_days + m.holidays + m.workdays).all()
    assert m[m.year == 2026].workdays.sum() == CORP.workdays_between(dt.date(2026, 1, 1), dt.date(2026, 12, 31))


def test_workdays_by_month_filters_months():
    m = FED.workdays_by_month(2026, months=[2])
    assert m[["year", "month", "workdays"]].values.tolist() == [[2026, 2, 19]]  # 20 weekdays - Washington's Birthday


# ---------------------------------------------------------------- dim_date
@pytest.fixture(scope="module")
def dim():
    return CORP.date_dimension(dt.date(2025, 1, 1), dt.date(2027, 12, 31), fiscal_year_start_month=10)


def test_dim_date_one_row_per_day(dim):
    assert len(dim) == 365 + 365 + 365
    assert dim.date.is_unique


def test_dim_date_flags_are_consistent(dim):
    assert (dim.is_workday == (~dim.is_weekend & ~dim.is_holiday)).all()
    assert dim.workday_of_month.isna().equals(~dim.is_workday)
    per_month = dim.groupby(["year", "month"])
    assert (per_month.workday_of_month.max() == per_month.workdays_in_month.first()).all()
    assert (dim.workdays_remaining_in_month >= 0).all()


def test_dim_date_holiday_names(dim):
    row = dim.set_index("date").loc[dt.date(2026, 11, 27)]
    assert row.holiday_name == "Day after Thanksgiving"
    assert not row.is_workday


@pytest.mark.parametrize(
    ("day", "fiscal_year", "fiscal_quarter"),
    [(dt.date(2025, 9, 30), 2025, 4), (dt.date(2025, 10, 1), 2026, 1), (dt.date(2026, 1, 15), 2026, 2), (dt.date(2026, 9, 30), 2026, 4)],
)
def test_dim_date_fiscal_calendar(dim, day, fiscal_year, fiscal_quarter):
    row = dim.set_index("date").loc[day]
    assert (row.fiscal_year, row.fiscal_quarter) == (fiscal_year, fiscal_quarter)


def test_dim_date_calendar_fiscal_year_by_default():
    d = FED.date_dimension(dt.date(2026, 12, 31), dt.date(2027, 1, 1))
    assert d.fiscal_year.tolist() == [2026, 2027]
    assert d.fiscal_quarter.tolist() == [4, 1]


def test_dim_date_partial_month_keeps_month_level_columns(dim):
    # Regression: a range that cuts a month used to count only the workdays inside the range.
    partial = CORP.date_dimension(dt.date(2026, 11, 24), dt.date(2026, 11, 30), fiscal_year_start_month=10)
    full = dim[(dim.date >= dt.date(2026, 11, 24)) & (dim.date <= dt.date(2026, 11, 30))].reset_index(drop=True)
    assert partial.equals(full)
    assert partial.workdays_in_month.iloc[0] == 19
