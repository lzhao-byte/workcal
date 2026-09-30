"""Command-line interface: ``workcal <command> --policy <preset or .toml> ...``"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from .calendar import WorkCalendar, source_holiday_names
from .policy import PolicyError, list_presets, load_policy


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _write(df, out: str | None) -> None:
    if out is None:
        print(df.to_string(index=False))
    elif out.endswith(".parquet"):
        df.to_parquet(out, index=False)
    else:
        df.to_csv(out, index=False)
    if out:
        print(f"wrote {len(df):,} rows to {out}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workcal", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("presets", help="list built-in holiday policies")

    def with_policy(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("-p", "--policy", default="us-federal", help="preset name or path to a .toml policy (default: us-federal)")
        return p

    p = with_policy(sub.add_parser("days-off", help="list days off in a date range"))
    p.add_argument("start", type=_date)
    p.add_argument("end", type=_date)
    p.add_argument("-o", "--out", help="write CSV/Parquet instead of printing")

    p = with_policy(sub.add_parser("count", help="count workdays in [start, end], inclusive"))
    p.add_argument("start", type=_date)
    p.add_argument("end", type=_date)

    p = with_policy(sub.add_parser("add", help="date N workdays after (or before, if negative) a date"))
    p.add_argument("date", type=_date)
    p.add_argument("n", type=int)

    p = with_policy(sub.add_parser("by-month", help="workdays per month"))
    p.add_argument("start_year", type=int)
    p.add_argument("end_year", type=int, nargs="?")
    p.add_argument("-m", "--months", type=int, nargs="+", help="only these months (1-12)")
    p.add_argument("-o", "--out")

    p = with_policy(sub.add_parser("dim-date", help="generate a dim_date table"))
    p.add_argument("start", type=_date)
    p.add_argument("end", type=_date)
    p.add_argument("--fiscal-start", type=int, default=1, help="first month of the fiscal year (default 1)")
    p.add_argument("-o", "--out", help="output .csv or .parquet (prints if omitted)")

    p = with_policy(sub.add_parser("source-holidays", help="every holiday name in the policy's source calendar"))
    p.add_argument("year", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "presets":
            for name in list_presets():
                print(f"{name:24} {load_policy(name).name}")
            return 0
        if args.command == "source-holidays":
            print("\n".join(source_holiday_names(load_policy(args.policy), args.year)))
            return 0

        cal = WorkCalendar.from_preset(str(Path(args.policy)) if args.policy.endswith(".toml") else args.policy)
        if args.command == "days-off":
            _write(cal.days_off(args.start, args.end), args.out)
        elif args.command == "count":
            print(cal.workdays_between(args.start, args.end))
        elif args.command == "add":
            print(cal.add_workdays(args.date, args.n).isoformat())
        elif args.command == "by-month":
            _write(cal.workdays_by_month(args.start_year, args.end_year, args.months), args.out)
        elif args.command == "dim-date":
            _write(cal.date_dimension(args.start, args.end, args.fiscal_start), args.out)
    except (PolicyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
