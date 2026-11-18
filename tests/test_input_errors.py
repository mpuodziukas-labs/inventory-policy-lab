"""Bad files and arguments raise one named ValueError, never a raw library error."""
import csv
import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast, pipeline, regen  # noqa: E402
from policy.formulas import eoq  # noqa: E402


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    for name in ("weekly_demand.csv", "sku_price.csv"):
        shutil.copy(ROOT / "data" / name, tmp_path / "data" / name)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    return tmp_path


def raised(fn, *args):
    with pytest.raises(Exception) as err:
        fn(*args)
    return err.value


@pytest.mark.parametrize("text", ["null", "5", "1.5", "true", '"text"', "[1, 2]", "[]"])
def test_a_config_that_is_valid_json_but_not_an_object_is_named(lab_dir, text):
    (lab_dir / "config.json").write_text(text, encoding="utf-8")
    for fn in (pipeline.load_config, pipeline.run):
        e = raised(fn)
        assert type(e) is ValueError
        assert str(e) == "config.json must be a JSON object"


LONG = "9" * 200000


@pytest.mark.parametrize("cell", [LONG, "x" * 200000])
def test_a_units_cell_over_the_csv_field_limit_gets_the_units_error(lab_dir, cell):
    (lab_dir / "data" / "weekly_demand.csv").write_text(f"iso_week,stock_code,units\n2010-W05,A,{cell}\n")
    e = raised(pipeline.load_series)
    assert type(e) is ValueError
    assert str(e) == "weekly_demand.csv: units for SKU A in week 2010-W05 must be a whole number of at least 0"


def test_a_price_cell_over_the_csv_field_limit_gets_the_price_error(lab_dir):
    (lab_dir / "data" / "sku_price.csv").write_text(f"stock_code,median_unit_price,description\nA,{LONG},a\n")
    e = raised(pipeline.load_prices)
    assert type(e) is ValueError
    assert str(e) == "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"


def test_the_csv_field_limit_is_back_to_its_old_value_after_a_read_and_after_a_failed_read(lab_dir):
    before = csv.field_size_limit()
    pipeline.load_series()
    assert csv.field_size_limit() == before
    (lab_dir / "data" / "weekly_demand.csv").write_text(f"iso_week,stock_code,units\n2010-W05,A,{LONG}\n")
    raised(pipeline.load_series)
    assert csv.field_size_limit() == before


def test_a_missing_config_is_named(lab_dir):
    (lab_dir / "config.json").unlink()
    for fn in (pipeline.load_config, pipeline.run):
        e = raised(fn)
        assert type(e) is ValueError
        assert str(e) == "config.json not found"
    assert type(e.__cause__) is FileNotFoundError


@pytest.mark.parametrize("name, fn", [("weekly_demand.csv", pipeline.load_series), ("sku_price.csv", pipeline.load_prices)])
def test_a_missing_data_file_is_named(lab_dir, name, fn):
    (lab_dir / "data" / name).unlink()
    e = raised(fn)
    assert type(e) is ValueError
    assert str(e) == f"{name}: file not found"
    assert type(e.__cause__) is FileNotFoundError


def test_run_names_the_missing_price_file_after_reading_the_demand_file(lab_dir):
    (lab_dir / "data" / "sku_price.csv").unlink()
    e = raised(pipeline.run)
    assert (type(e), str(e)) == (ValueError, "sku_price.csv: file not found")


def test_a_missing_readme_is_named_by_regen(tmp_path, monkeypatch):
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    e = raised(regen.main)
    assert type(e) is ValueError
    assert str(e) == "README.md not found"
    assert type(e.__cause__) is FileNotFoundError


@pytest.mark.parametrize("alpha", [0, -0.1, 1.0000001, 5, math.nan, math.inf, -math.inf])
def test_ses_rejects_an_alpha_outside_zero_to_one(alpha):
    e = raised(forecast.ses, [1, 2, 3], alpha)
    assert type(e) is ValueError
    assert str(e) == "ses alpha must be above 0 and at most 1"


def test_ses_alpha_is_checked_before_the_series():
    e = raised(forecast.ses, [], 5)
    assert (type(e), str(e)) == (ValueError, "ses alpha must be above 0 and at most 1")


@pytest.mark.parametrize("alpha, expected", [(1, 3), (0.5, 2.25), (1e-9, 1.000000003)])
def test_ses_accepts_alpha_up_to_and_including_one(alpha, expected):
    assert forecast.ses([1, 2, 3], alpha) == pytest.approx(expected, abs=1e-12)


def test_a_wrong_type_argument_to_a_public_function_raises_type_error_not_value_error():
    """Director ruling: a string where a number is expected is a TypeError, as Python raises it, and is not wrapped."""
    e = raised(eoq, "5", 1, 1)
    assert type(e) is TypeError
