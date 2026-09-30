import pandas as pd

from workcal.cli import main


def test_count(capsys):
    assert main(["count", "2026-01-01", "2026-01-31"]) == 0
    assert capsys.readouterr().out.strip() == "20"


def test_add(capsys):
    assert main(["add", "2026-11-25", "1", "-p", "us-corporate-example"]) == 0
    assert capsys.readouterr().out.strip() == "2026-11-30"


def test_presets(capsys):
    assert main(["presets"]) == 0
    assert "us-federal" in capsys.readouterr().out


def test_dim_date_to_csv(tmp_path):
    out = tmp_path / "dim_date.csv"
    assert main(["dim-date", "2026-01-01", "2026-12-31", "-o", str(out)]) == 0
    df = pd.read_csv(out)
    assert len(df) == 365
    assert df.is_workday.sum() == 250  # 261 weekdays - 11 federal holidays


def test_custom_policy_file(tmp_path, capsys):
    policy = tmp_path / "acme.toml"
    policy.write_text('name = "Acme"\ncountry = "US"\nobserve = ["Christmas Day"]\n')
    assert main(["count", "2026-12-21", "2026-12-25", "-p", str(policy)]) == 0
    assert capsys.readouterr().out.strip() == "4"


def test_bad_policy_exits_2(capsys):
    assert main(["count", "2026-01-01", "2026-01-31", "-p", "atlantis"]) == 2
    assert "no preset" in capsys.readouterr().err
