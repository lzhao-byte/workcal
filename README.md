# Workday Calculator

A small Streamlit app and Python utility that counts working days and lists observed holidays for any year, month, or date range. The holiday rules are configurable, so one tool works for different company calendars.

## Features

- **Flexible inputs:** a single year or a year range, optionally limited to specific months, or an explicit start and end date
- **Configurable holiday calendar:** a base set of US holidays (New Year's Day, MLK Day, Memorial Day, Independence Day, Labor Day, Thanksgiving + the day after, Christmas), with optional Juneteenth, Good Friday, Veterans Day, Columbus Day, and a year-end **Christmas shutdown** week
- **Weekend observance rules:** a Saturday holiday is observed the Friday before and a Sunday holiday the Monday after. New Year's Day is a special case: when it falls on a Saturday, it is observed the following Monday rather than in the previous year.
- **Outputs:** a table of holidays with their observed dates, and workdays per month (or the total for a date range). The Python function can also export both tables to Excel.

Built on the [`holidays`](https://pypi.org/project/holidays/) package and pandas custom business-day ranges (`bdate_range(freq="C")`).

## Run

```bash
pip install -r requirements.txt
streamlit run webapp.py
```

Or use it directly from Python:

```python
from utils import count_x_workdays

holidays, workdays = count_x_workdays(year_range=2026, include_juneteeth=True)
```

The repo also includes a `.devcontainer` for GitHub Codespaces. `get_workdays.ipynb` has more usage examples.
