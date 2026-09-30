"""WorkCalendar: turns a Policy into concrete days off, workday counts, and a date dimension."""

from __future__ import annotations

import datetime as dt
import difflib
from dataclasses import dataclass
from functools import lru_cache

import holidays as holidays_lib
import numpy as np
import pandas as pd
from dateutil.easter import easter

from .policy import DateSpec, Policy, PolicyError, load_policy, names_match

# Years used to check that every holiday named in a policy exists in the source calendar.
_VALIDATION_YEARS = range(2021, 2031)


@dataclass(frozen=True)
class DayOff:
    observed: dt.date  # the day people actually take off
    actual: dt.date  # the calendar date of the holiday itself
    name: str
    kind: str  # "public", "extra", or "shutdown"


class WorkCalendar:
    """A working-day calendar for one holiday policy.

    >>> cal = WorkCalendar.from_preset("us-federal")
    >>> cal.workdays_between(dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    20
    """

    def __init__(self, policy: Policy):
        self.policy = policy
        self._weekmask = "".join("0" if d in policy.weekend else "1" for d in range(7))
        self._validate_names()

    @classmethod
    def from_preset(cls, source: str) -> WorkCalendar:
        """Build from a built-in preset name or a path to a .toml policy file."""
        return cls(load_policy(source))

    # ------------------------------------------------------------------ source holidays
    def _source(self, year: int, observed: bool) -> list[tuple[dt.date, str]]:
        p = self.policy
        if p.market:
            cal = holidays_lib.financial_holidays(p.market, years=year)
        else:
            cal = holidays_lib.country_holidays(p.country, subdiv=p.subdiv, years=year, observed=observed)
        # python-holidays joins names that share a date with "; "
        return sorted((d, n.strip()) for d, names in cal.items() for n in names.split(";"))

    def _canonical(self, source_name: str) -> str | None:
        """The policy's own spelling of a source holiday, or None if the policy doesn't observe it."""
        if self.policy.observe is None:
            return source_name
        return next((n for n in self.policy.observe if names_match(n, source_name)), None)

    def _validate_names(self) -> None:
        p = self.policy
        known = {n for y in _VALIDATION_YEARS for _, n in self._source(y, observed=False)}
        referenced = list(p.observe or []) + list(p.shift_overrides)
        referenced += [s.holiday or s.observed for e in p.extras for s in [e.date] if s.holiday or s.observed]
        extra_names = [e.name for e in p.extras]
        for name in referenced:
            if not any(names_match(name, k) for k in known) and not any(names_match(name, e) for e in extra_names):
                hint = difflib.get_close_matches(name, sorted(known), n=3)
                raise PolicyError(
                    f"{p.name}: no holiday called {name!r} in the source calendar" + (f"; did you mean {hint}?" if hint else "")
                )

    # ------------------------------------------------------------------ observance
    def _is_weekend(self, d: dt.date) -> bool:
        return d.weekday() in self.policy.weekend

    def _step_to_workday(self, d: dt.date, step: int) -> dt.date:
        d += dt.timedelta(days=step)
        while self._is_weekend(d):
            d += dt.timedelta(days=step)
        return d

    def _observe(self, actual: dt.date, name: str) -> dt.date:
        if not self._is_weekend(actual):
            return actual
        rule = self.policy.shift_rule(name)
        if rule == "none":
            return actual
        if rule == "previous_workday":
            return self._step_to_workday(actual, -1)
        if rule == "next_workday":
            return self._step_to_workday(actual, 1)
        # nearest_workday: whichever side is closer; ties go forward
        before, after = self._step_to_workday(actual, -1), self._step_to_workday(actual, 1)
        return before if (actual - before) < (after - actual) else after

    def _resolve(self, spec: DateSpec, year: int, days: list[DayOff], public: list[tuple[dt.date, str]], where: str) -> dt.date:
        if spec.month is not None:
            base = dt.date(year, spec.month, spec.day)
        elif spec.easter:
            base = easter(year)
        elif spec.observed is not None:
            match = [d.observed for d in days if names_match(d.name, spec.observed)]
            if not match:
                raise PolicyError(f"{where}: {spec.observed!r} is not a day off in {year}")
            base = match[0]
        else:
            match = [d for d, n in public if names_match(n, spec.holiday)] or [d.actual for d in days if names_match(d.name, spec.holiday)]
            if not match:
                raise PolicyError(f"{where}: no holiday {spec.holiday!r} in {year}")
            base = match[0]
        return base + dt.timedelta(days=spec.offset_days)

    # ------------------------------------------------------------------ days off per year
    @lru_cache(maxsize=256)  # noqa: B019 - calendars are few and long-lived
    def _days_off(self, year: int) -> tuple[DayOff, ...]:
        """All days off whose underlying holiday belongs to ``year`` (the observed date may spill into
        an adjacent year, e.g. New Year's Day on a Saturday observed on Friday Dec 31)."""
        p = self.policy
        public = self._source(year, observed=False)
        days: list[DayOff] = []

        if p.official_observance or p.market:
            # Use the source's own observance rules (and closure dates for markets) as-is.
            for d, n in self._source(year, observed=True):
                canonical = self._canonical(n)
                if canonical is not None:
                    days.append(DayOff(d, d, canonical, "public"))
        else:
            for d, n in public:
                canonical = self._canonical(n)
                if canonical is not None:
                    days.append(DayOff(self._observe(d, canonical), d, canonical, "public"))

        for extra in p.extras:
            actual = self._resolve(extra.date, year, days, public, f"extra {extra.name!r}")
            days.append(DayOff(self._observe(actual, extra.name), actual, extra.name, "extra"))

        if p.on_collision == "next_workday":
            days = self._resolve_collisions(days)

        for sd in p.shutdowns:
            start = self._resolve(sd.start, year, days, public, f"shutdown {sd.name!r}")
            end = self._resolve(sd.end, year, days, public, f"shutdown {sd.name!r}")
            if end < start:
                raise PolicyError(f"shutdown {sd.name!r} ends before it starts in {year}")
            days = [d for d in days if not any(names_match(d.name, r) for r in sd.replaces)]
            span = pd.date_range(start, end).date
            days += [DayOff(d, d, sd.name, "shutdown") for d in span]

        return tuple(sorted(days, key=lambda d: (d.observed, d.name)))

    def _resolve_collisions(self, days: list[DayOff]) -> list[DayOff]:
        """If a holiday moved off a weekend lands on a day that is already off (or another holiday
        lands on its substitute day), push the later holiday to the next free workday.
        UK example: Christmas on Saturday -> Monday, so Boxing Day (Sunday) -> Tuesday."""
        taken: dict[dt.date, bool] = {}  # observed date -> was that holiday shifted off a weekend?
        out = []
        for d in sorted(days, key=lambda d: (d.actual, d.name)):
            observed, shifted = d.observed, d.observed != d.actual
            if observed in taken and (shifted or taken[observed]):
                while observed in taken or self._is_weekend(observed):
                    observed += dt.timedelta(days=1)
            taken.setdefault(observed, shifted)
            out.append(DayOff(observed, d.actual, d.name, d.kind))
        return out

    # ------------------------------------------------------------------ public API
    def days_off(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Every day off observed in [start, end], one row per (date, holiday)."""
        rows = [d for y in range(start.year - 1, end.year + 2) for d in self._days_off(y) if start <= d.observed <= end]
        df = pd.DataFrame(rows, columns=["observed", "actual", "name", "kind"])
        return df.sort_values(["observed", "name"]).reset_index(drop=True)

    def _holiday_array(self, start: dt.date, end: dt.date) -> np.ndarray:
        return np.array(sorted(self.days_off(start, end).observed.unique()), dtype="datetime64[D]")

    def is_workday(self, d: dt.date) -> bool:
        return bool(np.is_busday(np.datetime64(d, "D"), weekmask=self._weekmask, holidays=self._holiday_array(d, d)))

    def workdays_between(self, start: dt.date, end: dt.date) -> int:
        """Number of workdays in [start, end], both ends inclusive."""
        if end < start:
            raise ValueError("end must not be before start")
        return int(
            np.busday_count(
                np.datetime64(start, "D"),
                np.datetime64(end + dt.timedelta(days=1), "D"),
                weekmask=self._weekmask,
                holidays=self._holiday_array(start, end),
            )
        )

    def add_workdays(self, d: dt.date, n: int) -> dt.date:
        """The date ``n`` workdays after ``d`` (before, if negative), like Excel's WORKDAY().
        ``d`` itself is not counted, and n == 0 returns ``d`` unchanged."""
        if n == 0:
            return d
        pad = dt.timedelta(days=abs(n) * 2 + 60)
        holidays = self._holiday_array(d - pad, d + pad)
        roll = "backward" if n > 0 else "forward"
        out = np.busday_offset(np.datetime64(d, "D"), n, roll=roll, weekmask=self._weekmask, holidays=holidays)
        return out.astype(dt.date)

    def workdays_by_month(self, start_year: int, end_year: int | None = None, months: list[int] | None = None) -> pd.DataFrame:
        """Workdays per month, with the calendar-day breakdown:
        calendar_days == weekend_days + holidays + workdays."""
        end_year = end_year or start_year
        dim = self.date_dimension(dt.date(start_year, 1, 1), dt.date(end_year, 12, 31))
        if months:
            dim = dim[dim.month.isin(months)]
        dim = dim.assign(weekday_holiday=dim.is_holiday & ~dim.is_weekend)
        g = dim.groupby(["year", "month"])
        out = pd.DataFrame(
            {
                "calendar_days": g.size(),
                "weekend_days": g.is_weekend.sum(),
                "holidays": g.weekday_holiday.sum(),
                "workdays": g.is_workday.sum(),
            }
        )
        return out.reset_index()

    def date_dimension(self, start: dt.date, end: dt.date, fiscal_year_start_month: int = 1) -> pd.DataFrame:
        """A ``dim_date`` table: one row per calendar day with workday attributes.

        Fiscal years are labeled by the calendar year they end in (FY starting Oct 2025 = FY2026).
        """
        if not 1 <= fiscal_year_start_month <= 12:
            raise ValueError("fiscal_year_start_month must be 1-12")
        # Build whole months so month-level columns are right even when [start, end] cuts a month.
        month_start = start.replace(day=1)
        month_end = (pd.Timestamp(end) + pd.offsets.MonthEnd(0)).date()
        dates = pd.date_range(month_start, month_end, freq="D")
        off = self.days_off(month_start, month_end)
        names = off.groupby("observed")["name"].agg(lambda s: "; ".join(dict.fromkeys(s)))

        df = pd.DataFrame({"date": dates.date})
        df["year"] = dates.year
        df["quarter"] = dates.quarter
        df["month"] = dates.month
        df["month_name"] = dates.month_name()
        df["day_of_month"] = dates.day
        df["day_of_week"] = dates.dayofweek + 1  # ISO: Monday = 1
        df["day_name"] = dates.day_name()
        iso = dates.isocalendar()
        df["iso_year"] = iso.year.to_numpy()
        df["iso_week"] = iso.week.to_numpy()
        df["is_weekend"] = dates.dayofweek.isin(self.policy.weekend)
        df["holiday_name"] = df["date"].map(names)
        df["is_holiday"] = df["holiday_name"].notna()
        df["is_workday"] = ~df.is_weekend & ~df.is_holiday

        ym = df.year * 100 + df.month
        df["workday_of_month"] = df.groupby(ym).is_workday.cumsum().where(df.is_workday).astype("Int64")
        df["workdays_in_month"] = df.groupby(ym).is_workday.transform("sum")
        df["workdays_remaining_in_month"] = df.workdays_in_month - df.groupby(ym).is_workday.cumsum()

        shifted = df.month - fiscal_year_start_month
        df["fiscal_year"] = df.year + (shifted >= 0).astype(int) * (fiscal_year_start_month != 1)
        df["fiscal_quarter"] = (shifted % 12) // 3 + 1
        return df[(df.date >= start) & (df.date <= end)].reset_index(drop=True)

    def __repr__(self) -> str:
        return f"WorkCalendar({self.policy.name!r})"


def source_holiday_names(policy: Policy, year: int) -> list[str]:
    """Every holiday name in the policy's source calendar for ``year``, whether or not the policy
    observes it. Handy when writing the ``observe`` list of a new policy."""
    cal = WorkCalendar(
        Policy.from_dict(
            {"name": "all", **({"market": policy.market} if policy.market else {"country": policy.country, "subdiv": policy.subdiv})}
        )
    )
    return sorted({n for _, n in cal._source(year, observed=False)})
