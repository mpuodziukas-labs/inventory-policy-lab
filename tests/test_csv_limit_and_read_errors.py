"""csv field limit is lifted for a read and always put back; only a missing file is renamed to ValueError."""
import csv
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402

H_DEMAND = "iso_week,stock_code,units"
H_PRICE = "stock_code,median_unit_price,description"
LONG = "x" * 300000  # above 2**18 = 262144, below the lifted limit


def exact(text):
    return "^" + re.escape(text) + "$"


@pytest.fixture
def saved_limit():
    """Every test that touches the csv limit goes through here, so none leaks state."""
    prior = csv.field_size_limit()
    try:
        yield prior
    finally:
        csv.field_size_limit(prior)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    return tmp_path


def as_directory(d, rel):
    f = d / rel
    f.unlink()
    f.mkdir()


# ---- only a missing file becomes ValueError; any other read error keeps its own type

def test_config_json_that_is_a_directory_raises_isadirectoryerror_not_valueerror(lab):
    as_directory(lab, "config.json")
    with pytest.raises(IsADirectoryError):
        pipeline.load_config()


def test_demand_file_that_is_a_directory_raises_isadirectoryerror_not_valueerror(lab, saved_limit):
    as_directory(lab, "data/weekly_demand.csv")
    with pytest.raises(IsADirectoryError):
        pipeline.load_series()


def test_price_file_that_is_a_directory_raises_isadirectoryerror_not_valueerror(lab, saved_limit):
    as_directory(lab, "data/sku_price.csv")
    with pytest.raises(IsADirectoryError):
        pipeline.load_prices()


def test_readme_that_is_a_directory_raises_isadirectoryerror_not_valueerror_through_regen_main(lab):
    as_directory(lab, "README.md")
    with pytest.raises(IsADirectoryError):
        regen.main()


# ---- a cell above 2**18 characters still reaches the named check

def test_a_300000_character_units_cell_gets_the_named_units_error_not_a_csv_error(lab, saved_limit):
    (lab / "data" / "weekly_demand.csv").write_text(f"{H_DEMAND}\n2011-W01,A,{LONG}\n", encoding="utf-8")
    msg = "weekly_demand.csv: units for SKU A in week 2011-W01 must be a whole number of at least 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.load_series()


def test_a_300000_character_price_cell_gets_the_named_price_error_not_a_csv_error(lab, saved_limit):
    (lab / "data" / "sku_price.csv").write_text(f"{H_PRICE}\nA,{LONG},bag\n", encoding="utf-8")
    msg = "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.load_prices()


# ---- the limit is restored to its prior value on every path

def test_limit_is_restored_to_its_prior_value_after_a_successful_demand_load(lab, saved_limit):
    csv.field_size_limit(5000)
    assert pipeline.load_series()
    assert csv.field_size_limit() == 5000


def test_limit_is_restored_to_its_prior_value_after_a_successful_price_load(lab, saved_limit):
    csv.field_size_limit(5000)
    assert pipeline.load_prices()
    assert csv.field_size_limit() == 5000


def test_limit_is_restored_after_a_missing_column_error_in_the_demand_file(lab, saved_limit):
    (lab / "data" / "weekly_demand.csv").write_text("iso_week,stock_code\n2011-W01,A\n", encoding="utf-8")
    csv.field_size_limit(5000)
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: missing column units")):
        pipeline.load_series()
    assert csv.field_size_limit() == 5000


def test_limit_is_restored_after_a_missing_column_error_in_the_price_file(lab, saved_limit):
    (lab / "data" / "sku_price.csv").write_text("stock_code,description\nA,bag\n", encoding="utf-8")
    csv.field_size_limit(5000)
    with pytest.raises(ValueError, match=exact("sku_price.csv: missing column median_unit_price")):
        pipeline.load_prices()
    assert csv.field_size_limit() == 5000


def test_limit_is_restored_after_a_missing_file_error(lab, saved_limit):
    (lab / "data" / "weekly_demand.csv").unlink()
    csv.field_size_limit(5000)
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: file not found")):
        pipeline.load_series()
    assert csv.field_size_limit() == 5000


def test_limit_is_restored_after_a_directory_read_error(lab, saved_limit):
    as_directory(lab, "data/sku_price.csv")
    csv.field_size_limit(5000)
    with pytest.raises(IsADirectoryError):
        pipeline.load_prices()
    assert csv.field_size_limit() == 5000
