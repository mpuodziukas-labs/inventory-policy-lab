"""The demand and price files are checked as they are read; each defect gets one clear message."""
import csv
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402


def _stub_sim(history, rop, q, lv, lp, seed, weeks, warmup):
    return {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
            "avg_inventory": 1.0, "turns": 1.0, "orders": 1}


def _units(k, n):
    return [(i * 7 + k * 3) % 11 + 1 for i in range(n)]


def _week(i):
    return f"2011-W{i + 1:02d}"


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", _stub_sim)
    return tmp_path


def write_files(d, lengths, demand_rows=None, price_rows=None, demand_header="iso_week,stock_code,units",
                price_header="stock_code,median_unit_price,description"):
    """lengths maps a SKU code to its number of weeks; rows can be replaced to plant a defect."""
    if demand_rows is None:
        demand_rows = [f"{_week(i)},{code},{u}" for k, (code, n) in enumerate(lengths.items())
                       for i, u in enumerate(_units(k, n))]
    if price_rows is None:
        price_rows = [f"{code},2.50,item {code}" for code in lengths]
    (d / "data" / "weekly_demand.csv").write_text("\n".join([demand_header, *demand_rows]) + "\n")
    (d / "data" / "sku_price.csv").write_text("\n".join([price_header, *price_rows]) + "\n")


def exact(text):
    return re.escape(text)


@pytest.mark.parametrize("lengths, message", [
    ({"A": 52, "B": 53}, "SKU B has 53 weeks but SKU A has 52; every SKU needs the same number of weeks"),
    ({"A": 53, "B": 52}, "SKU B has 52 weeks but SKU A has 53; every SKU needs the same number of weeks"),
    ({"A": 52, "B": 52, "C": 53, "D": 54}, "SKU C has 53 weeks but SKU A has 52; every SKU needs the same number of weeks"),
])
def test_ragged_series_name_the_first_differing_sku_the_first_sku_and_both_lengths(lab_dir, lengths, message):
    write_files(lab_dir, lengths)
    with pytest.raises(ValueError, match=exact(message)):
        pipeline.run()


def test_equal_length_series_are_accepted(lab_dir):
    write_files(lab_dir, {"A": 52, "B": 52})
    assert pipeline.run()["summary"]["weeks"] == 52


def test_an_empty_description_stays_the_empty_string_in_the_sku_row(lab_dir):
    write_files(lab_dir, {"A": 52, "B": 52}, price_rows=["A,2.50,", "B,2.50,bag"])
    rows = {r["code"]: r for r in pipeline.run()["skus"]}
    assert rows["A"]["description"] == ""
    assert rows["B"]["description"] == "bag"


def test_a_duplicate_sku_week_row_is_rejected_naming_the_sku_and_week(lab_dir):
    rows = [f"{_week(i)},A,{u}" for i, u in enumerate(_units(0, 52))] + ["2011-W03,A,4"]
    write_files(lab_dir, {"A": 52}, demand_rows=rows)
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: duplicate row for SKU A in week 2011-W03")):
        pipeline.run()


def test_the_same_week_for_two_different_skus_is_not_a_duplicate(lab_dir):
    write_files(lab_dir, {"A": 52, "B": 52})
    assert pipeline.run()["summary"]["sku_count"] == 2


def test_a_header_only_demand_file_is_rejected_not_a_stop_iteration(lab_dir):
    write_files(lab_dir, {"A": 52}, demand_rows=[])
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: no data rows")):
        pipeline.run()


@pytest.mark.parametrize("column", ["iso_week", "stock_code", "units"])
def test_a_demand_file_missing_a_column_names_the_column(lab_dir, column):
    header = ",".join(c for c in ("iso_week", "stock_code", "units") if c != column)
    write_files(lab_dir, {"A": 52}, demand_rows=["x,y"], demand_header=header)
    with pytest.raises(ValueError, match=exact(f"weekly_demand.csv: missing column {column}")):
        pipeline.run()


@pytest.mark.parametrize("column", ["stock_code", "median_unit_price", "description"])
def test_a_price_file_missing_a_column_names_the_column(lab_dir, column):
    header = ",".join(c for c in ("stock_code", "median_unit_price", "description") if c != column)
    write_files(lab_dir, {"A": 52}, price_rows=["x,y"], price_header=header)
    with pytest.raises(ValueError, match=exact(f"sku_price.csv: missing column {column}")):
        pipeline.run()


@pytest.mark.parametrize("cell", ["abc", "", "1.5", "nan", "-3", "1e3"])
def test_a_units_cell_that_is_not_a_whole_number_of_at_least_zero_is_rejected(lab_dir, cell):
    rows = [f"{_week(i)},A,{u}" for i, u in enumerate(_units(0, 52))]
    rows[1] = f"2011-W02,A,{cell}"
    write_files(lab_dir, {"A": 52}, demand_rows=rows)
    msg = "weekly_demand.csv: units for SKU A in week 2011-W02 must be a whole number of at least 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


def test_a_units_cell_of_zero_is_accepted(lab_dir):
    rows = [f"{_week(i)},A,{u}" for i, u in enumerate(_units(0, 52))]
    rows[1] = "2011-W02,A,0"
    write_files(lab_dir, {"A": 52}, demand_rows=rows)
    assert pipeline.run()["summary"]["weeks"] == 52


def test_a_short_row_is_rejected_like_any_bad_units_cell(lab_dir):
    rows = [f"{_week(i)},A,{u}" for i, u in enumerate(_units(0, 52))]
    rows[1] = "2011-W02,A"
    write_files(lab_dir, {"A": 52}, demand_rows=rows)
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: units for SKU A in week 2011-W02 must be")):
        pipeline.run()


def test_a_sku_in_the_demand_file_but_not_in_the_price_file_is_rejected(lab_dir):
    write_files(lab_dir, {"A": 52, "B": 52}, price_rows=["A,2.50,bag"])
    with pytest.raises(ValueError, match=exact("sku_price.csv: no price row for SKU B")):
        pipeline.run()


def test_a_header_only_price_file_leaves_every_sku_without_a_price(lab_dir):
    write_files(lab_dir, {"A": 52}, price_rows=[])
    with pytest.raises(ValueError, match=exact("sku_price.csv: no price row for SKU A")):
        pipeline.run()


@pytest.mark.parametrize("cell", ["nan", "inf", "-inf", "0", "-1", "-0.5", "abc", ""])
def test_a_price_that_is_not_finite_and_above_zero_is_rejected(lab_dir, cell):
    write_files(lab_dir, {"A": 52}, price_rows=[f"A,{cell},bag"])
    msg = "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


def test_the_vendored_files_still_load_with_forty_skus_of_equal_length():
    series = pipeline.load_series()
    prices = pipeline.load_prices()
    assert len(series) == 40
    assert len({len(v) for v in series.values()}) == 1
    assert set(series) <= set(prices)
    with open(ROOT / "data" / "sku_price.csv", newline="") as f:
        first = next(csv.DictReader(f))
    assert prices[first["stock_code"]] == (float(first["median_unit_price"]), first["description"])
