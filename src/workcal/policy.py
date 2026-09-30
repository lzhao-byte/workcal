"""Holiday policies: which days an organization takes off, and how weekend holidays are observed.

A policy is plain data, loaded from TOML (see ``presets/`` for examples) or built from a dict.
Validation happens here, so a typo in a config file fails loudly at load time instead of
silently producing a wrong workday count.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SHIFT_RULES = ("none", "nearest_workday", "previous_workday", "next_workday")
COLLISION_RULES = ("keep", "next_workday")


class PolicyError(ValueError):
    """Raised when a holiday policy is invalid."""


def normalize_name(name: str) -> str:
    """Normalize a holiday name for matching: case, curly quotes, and '(observed)' suffixes."""
    name = name.casefold().replace("’", "'")
    name = re.sub(r"\s*\((observed|estimated)\)", "", name)
    return re.sub(r"\s+", " ", name).strip()


def names_match(a: str, b: str) -> bool:
    """True if two holiday names refer to the same holiday.

    Tolerates renames that only add a trailing word, e.g. "Thanksgiving" vs "Thanksgiving Day"
    (python-holidays renamed it between versions, which silently broke v1 of this tool).
    """
    a, b = normalize_name(a), normalize_name(b)
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


@dataclass(frozen=True)
class DateSpec:
    """A date within a given year.

    Exactly one anchor is set: a fixed ``month``/``day``, the actual date of a named ``holiday``,
    the *observed* date of a named holiday (``observed``), or an offset from Western ``easter``.
    ``offset_days`` is added to the anchor.
    """

    month: int | None = None
    day: int | None = None
    holiday: str | None = None
    observed: str | None = None
    easter: bool = False
    offset_days: int = 0

    @classmethod
    def parse(cls, raw: Any, where: str) -> DateSpec:
        if not isinstance(raw, dict):
            raise PolicyError(f"{where}: expected a table like {{ month = 12, day = 24 }}, got {raw!r}")
        unknown = set(raw) - {"month", "day", "holiday", "observed", "easter", "offset_days"}
        if unknown:
            raise PolicyError(f"{where}: unknown keys {sorted(unknown)}")
        spec = cls(
            month=raw.get("month"),
            day=raw.get("day"),
            holiday=raw.get("holiday"),
            observed=raw.get("observed"),
            easter="easter" in raw,
            offset_days=int(raw.get("offset_days", 0)) + (int(raw["easter"]) if "easter" in raw else 0),
        )
        anchors = [spec.month is not None, spec.holiday is not None, spec.observed is not None, spec.easter]
        if sum(anchors) != 1:
            raise PolicyError(f"{where}: set exactly one of month/day, holiday, observed, or easter")
        if spec.month is not None and (spec.day is None or not 1 <= spec.month <= 12 or not 1 <= spec.day <= 31):
            raise PolicyError(f"{where}: invalid month/day {spec.month}/{spec.day}")
        return spec


@dataclass(frozen=True)
class ExtraDay:
    """A company-specific day off that is not a public holiday (e.g. the day after Thanksgiving)."""

    name: str
    date: DateSpec


@dataclass(frozen=True)
class Shutdown:
    """A block of consecutive days off, e.g. a year-end shutdown. Every calendar day in
    [start, end] is a non-workday. Holidays listed in ``replaces`` are folded into it."""

    name: str
    start: DateSpec
    end: DateSpec
    replaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class Policy:
    name: str
    description: str = ""
    country: str | None = None
    subdiv: str | None = None
    market: str | None = None
    observe: tuple[str, ...] | None = None  # None means every holiday from the source
    weekend: tuple[int, ...] = (5, 6)  # Monday == 0
    official_observance: bool = False
    shift_default: str = "nearest_workday"
    shift_overrides: dict[str, str] = field(default_factory=dict)
    on_collision: str = "keep"
    extras: tuple[ExtraDay, ...] = ()
    shutdowns: tuple[Shutdown, ...] = ()

    def shift_rule(self, holiday_name: str) -> str:
        for name, rule in self.shift_overrides.items():
            if names_match(name, holiday_name):
                return rule
        return self.shift_default

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Policy:
        known = {"name", "description", "country", "subdiv", "market", "observe", "weekend", "observance", "extra", "shutdown"}
        unknown = set(raw) - known
        if unknown:
            raise PolicyError(f"unknown top-level keys {sorted(unknown)}")
        if "name" not in raw:
            raise PolicyError("a policy needs a name")
        if bool(raw.get("country")) == bool(raw.get("market")):
            raise PolicyError("set exactly one of 'country' (e.g. \"US\") or 'market' (e.g. \"NYSE\")")

        weekend_raw = raw.get("weekend", ["sat", "sun"])
        try:
            weekend = tuple(sorted(WEEKDAY_NAMES.index(d.lower()[:3]) for d in weekend_raw))
        except ValueError as exc:
            raise PolicyError(f"weekend days must be from {WEEKDAY_NAMES}, got {weekend_raw}") from exc
        if len(weekend) >= 7:
            raise PolicyError("weekend cannot cover the whole week")

        obs = raw.get("observance", {})
        unknown = set(obs) - {"official", "default", "on_collision", "overrides"}
        if unknown:
            raise PolicyError(f"observance: unknown keys {sorted(unknown)}")
        shift_default = obs.get("default", "nearest_workday")
        overrides = dict(obs.get("overrides", {}))
        for rule in [shift_default, *overrides.values()]:
            if rule not in SHIFT_RULES:
                raise PolicyError(f"observance rule must be one of {SHIFT_RULES}, got {rule!r}")
        on_collision = obs.get("on_collision", "keep")
        if on_collision not in COLLISION_RULES:
            raise PolicyError(f"on_collision must be one of {COLLISION_RULES}, got {on_collision!r}")

        extras = []
        for i, e in enumerate(raw.get("extra", [])):
            if "name" not in e or "date" not in e:
                raise PolicyError(f"extra[{i}]: needs 'name' and 'date'")
            extras.append(ExtraDay(e["name"], DateSpec.parse(e["date"], f"extra[{i}] ({e['name']})")))

        shutdowns = []
        for i, s in enumerate(raw.get("shutdown", [])):
            if not {"name", "start", "end"} <= set(s):
                raise PolicyError(f"shutdown[{i}]: needs 'name', 'start' and 'end'")
            shutdowns.append(
                Shutdown(
                    s["name"],
                    DateSpec.parse(s["start"], f"shutdown[{i}].start"),
                    DateSpec.parse(s["end"], f"shutdown[{i}].end"),
                    tuple(s.get("replaces", [])),
                )
            )

        observe = raw.get("observe")
        return cls(
            name=raw["name"],
            description=raw.get("description", ""),
            country=raw.get("country"),
            subdiv=raw.get("subdiv"),
            market=raw.get("market"),
            observe=tuple(observe) if observe is not None else None,
            weekend=weekend,
            official_observance=bool(obs.get("official", False)),
            shift_default=shift_default,
            shift_overrides=overrides,
            on_collision=on_collision,
            extras=tuple(extras),
            shutdowns=tuple(shutdowns),
        )


def _toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # JSON string escapes are valid TOML basic-string escapes
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items()) + " }" if value else "{}"
    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def dumps_policy(raw: dict[str, Any]) -> str:
    """Serialize a policy dict (the shape ``load_policy_dict`` returns) back to TOML.

    Covers the policy schema only (scalars, lists, tables, arrays of tables), so the app can offer
    "download this policy" without an extra dependency.
    """
    lines, tables, arrays = [], [], []
    for key, value in raw.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            arrays.append((key, value))
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, table in tables:
        lines += ["", f"[{_toml_key(key)}]", *(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in table.items())]
    for key, items in arrays:
        for item in items:
            lines += ["", f"[[{_toml_key(key)}]]", *(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in item.items())]
    return "\n".join(lines) + "\n"


def list_presets() -> list[str]:
    """Names of the built-in policies shipped in ``workcal/presets``."""
    return sorted(p.name.removesuffix(".toml") for p in resources.files("workcal.presets").iterdir() if p.name.endswith(".toml"))


def load_policy_dict(source: str | Path) -> dict[str, Any]:
    """Raw TOML dict for a preset name (e.g. ``"us-federal"``) or a path to a .toml file."""
    path = Path(source)
    if path.suffix == ".toml" and path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8"))
    if str(source) in list_presets():
        return tomllib.loads(resources.files("workcal.presets").joinpath(f"{source}.toml").read_text(encoding="utf-8"))
    raise PolicyError(f"no preset or .toml file named {source!r}; presets: {', '.join(list_presets())}")


def load_policy(source: str | Path) -> Policy:
    return Policy.from_dict(load_policy_dict(source))
