"""workcal: company holiday policies as config, and the working-day math on top of them."""

from .calendar import DayOff, WorkCalendar, source_holiday_names
from .policy import Policy, PolicyError, list_presets, load_policy

__all__ = ["DayOff", "Policy", "PolicyError", "WorkCalendar", "list_presets", "load_policy", "source_holiday_names"]
__version__ = "2.0.0"
