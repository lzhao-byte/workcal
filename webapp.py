"""Streamlit front end for workcal: pick or upload a holiday policy, tweak it, and get workday counts or a dim_date table."""

import copy
import datetime as dt
import tomllib

import streamlit as st
import tomli_w

from workcal import Policy, PolicyError, WorkCalendar, list_presets, source_holiday_names
from workcal.policy import WEEKDAY_NAMES, load_policy_dict, names_match

st.set_page_config(page_title="Workday Calculator", page_icon=":material/calendar_month:", layout="wide")
today = dt.date.today()

# ---------------------------------------------------------------- policy
with st.sidebar:
    st.header("Holiday policy")
    source = st.selectbox("Start from", [*list_presets(), "Upload a .toml file"], index=list_presets().index("us-corporate-example"))
    if source == "Upload a .toml file":
        upload = st.file_uploader("Policy file", type="toml")
        if upload is None:
            st.info("Upload a policy, or start from a preset and customize it below.")
            st.stop()
        raw = tomllib.loads(upload.getvalue().decode("utf-8"))
    else:
        raw = load_policy_dict(source)
    raw = copy.deepcopy(raw)
    st.caption(raw.get("description", ""))

    with st.expander("Customize", expanded=False):
        base = Policy.from_dict(raw)
        if not base.market:
            names = source_holiday_names(base, today.year)
            default = names if base.observe is None else [n for n in names if any(names_match(n, o) for o in base.observe)]
            raw["observe"] = st.multiselect("Public holidays observed", names, default=default)
            rules = ["nearest_workday", "previous_workday", "next_workday", "none"]
            obs = raw.setdefault("observance", {})
            obs["default"] = st.selectbox("Weekend holiday is observed on", rules, index=rules.index(obs.get("default", "nearest_workday")))
        raw["weekend"] = st.multiselect("Weekend days", list(WEEKDAY_NAMES), default=raw.get("weekend", ["sat", "sun"]))
        raw["extra"] = [e for e in raw.get("extra", []) if st.checkbox(f"Extra day off: {e['name']}", value=True)]
        raw["shutdown"] = [s for s in raw.get("shutdown", []) if st.checkbox(f"Shutdown: {s['name']}", value=True)]

    try:
        cal = WorkCalendar(Policy.from_dict(raw))
    except PolicyError as exc:
        st.error(str(exc), icon=":material/error:")
        st.stop()

    st.download_button("Download this policy (.toml)", tomli_w.dumps(raw), file_name="holiday_policy.toml")

# ---------------------------------------------------------------- outputs
st.title("Workday Calculator")
st.write(f"Policy: **{cal.policy.name}**")

days_tab, month_tab, math_tab, dim_tab = st.tabs(["Days off", "Workdays by month", "Date math", "dim_date table"])

with days_tab:
    c1, c2 = st.columns(2)
    start_year = c1.number_input("From year", 1950, 2100, today.year)
    end_year = c2.number_input("To year", 1950, 2100, today.year)
    if end_year < start_year:
        st.error("'To year' must not be before 'From year'.")
    else:
        off = cal.days_off(dt.date(start_year, 1, 1), dt.date(end_year, 12, 31))
        st.dataframe(
            off,
            hide_index=True,
            use_container_width=True,
            column_config={"observed": st.column_config.DateColumn("Day off"), "actual": st.column_config.DateColumn("Holiday date")},
        )

with month_tab:
    c1, c2, c3 = st.columns([1, 1, 2])
    y1 = c1.number_input("From year ", 1950, 2100, today.year)
    y2 = c2.number_input("To year ", 1950, 2100, today.year)
    months = c3.multiselect("Months (all if empty)", list(range(1, 13)), format_func=lambda m: dt.date(2000, m, 1).strftime("%B"))
    if y2 < y1:
        st.error("'To year' must not be before 'From year'.")
    else:
        by_month = cal.workdays_by_month(y1, y2, months or None)
        st.dataframe(by_month, hide_index=True, use_container_width=True)
        st.metric("Total workdays", f"{by_month.workdays.sum():,}")

with math_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Count workdays")
        a = st.date_input("Start", today.replace(month=1, day=1))
        b = st.date_input("End (inclusive)", today.replace(month=12, day=31))
        if b >= a:
            st.metric("Workdays", cal.workdays_between(a, b))
        else:
            st.error("End must not be before start.")
    with right:
        st.subheader("Add workdays (like Excel WORKDAY)")
        d = st.date_input("From date", today)
        n = st.number_input("Workdays to add (negative to go back)", -1000, 1000, 10)
        st.metric("Result", cal.add_workdays(d, int(n)).isoformat())

with dim_tab:
    c1, c2, c3 = st.columns(3)
    s = c1.date_input("Start date", dt.date(today.year, 1, 1))
    e = c2.date_input("End date", dt.date(today.year, 12, 31))
    fiscal = c3.selectbox("Fiscal year starts in", list(range(1, 13)), format_func=lambda m: dt.date(2000, m, 1).strftime("%B"))
    if e < s:
        st.error("End must not be before start.")
    else:
        dim = cal.date_dimension(s, e, fiscal)
        st.dataframe(dim, hide_index=True, use_container_width=True)
        st.download_button("Download CSV", dim.to_csv(index=False), file_name="dim_date.csv", mime="text/csv")
