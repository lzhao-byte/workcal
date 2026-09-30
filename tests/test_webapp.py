"""Smoke tests for the Streamlit app, run headless with Streamlit's AppTest."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parents[1] / "webapp.py")


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_app_renders_default_policy(app):
    assert "US corporate (example)" in app.markdown[0].value
    assert len(app.dataframe) >= 3  # days off, by month, dim_date
    assert app.metric[0].label == "Total workdays"


@pytest.mark.parametrize("preset", ["us-federal", "uk-england", "nyse"])
def test_every_preset_renders(app, preset):
    app.sidebar.selectbox[0].select(preset).run()
    assert not app.exception
    assert not app.error


def test_dropping_the_shutdown_adds_workdays(app):
    before = int(app.metric[0].value.replace(",", ""))
    shutdown = next(c for c in app.sidebar.checkbox if c.label.startswith("Shutdown"))
    shutdown.uncheck().run()
    after = int(app.metric[0].value.replace(",", ""))
    assert after > before


def test_days_off_use_the_policy_spelling_of_holiday_names(app):
    # python-holidays now calls it "Thanksgiving Day"; the preset says "Thanksgiving".
    names = set(app.dataframe[0].value["name"])
    assert "Thanksgiving" in names
    assert "Thanksgiving Day" not in names
