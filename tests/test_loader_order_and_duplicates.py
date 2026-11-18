"""Week order, a shared week list, duplicate price rows and padded price cells are rejected by name."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402


def exact(text):
    return "^" + re.escape(text) + "$"


@pytest.fixture
def put(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    def write(name, text):
        (tmp_path / "data" / name).write_text(text, encoding="utf-8")
    return write


def demand(put, rows):
    put("weekly_demand.csv", "iso_week,stock_code,units\n" + "".join(f"{w},{c},{u}\n" for w, c, u in rows))


def prices(put, rows):
    put("sku_price.csv", "stock_code,median_unit_price,description\n" + "".join(f"{c},{p},d\n" for c, p in rows))


def test_weeks_out_of_order_are_rejected_with_row_and_sku(put):
    demand(put, [("2011-W01", "A", 1), ("2011-W03", "A", 1), ("2011-W02", "A", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: row 4: weeks for SKU A must be in ascending order, "
            "but 2011-W02 follows 2011-W03")):
        pipeline.load_series()


def test_ascending_weeks_pass(put):
    demand(put, [("2011-W01", "A", 1), ("2011-W02", "A", 2), ("2011-W10", "A", 3)])
    assert pipeline.load_series() == {"A": [1, 2, 3]}


def test_skus_must_share_the_same_week_list(put):
    demand(put, [("2011-W01", "A", 1), ("2011-W02", "A", 1), ("2011-W01", "B", 1), ("2011-W03", "B", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: SKU B covers different weeks than SKU A")):
        pipeline.load_series()


def test_a_ragged_length_still_gets_the_length_error_from_run(put, tmp_path):
    """Different lengths are the run() error, not preempted by the week-list check."""
    demand(put, [("2011-W01", "A", 1), ("2011-W02", "A", 1), ("2011-W01", "B", 1)])
    assert pipeline.load_series() == {"A": [1, 1], "B": [1]}


def test_a_duplicate_stock_code_in_prices_is_named(put):
    prices(put, [("A", "1.00"), ("B", "2.00"), ("A", "3.00")])
    with pytest.raises(ValueError, match=exact("sku_price.csv: duplicate row for SKU A")):
        pipeline.load_prices()


@pytest.mark.parametrize("cell", [" 1.50", "1.50 ", "\t1.50"])
def test_a_price_with_surrounding_whitespace_is_named(put, cell):
    prices(put, [("A", cell)])
    with pytest.raises(ValueError, match=exact(
            f"sku_price.csv: median_unit_price for SKU A has surrounding whitespace: '{cell}'")):
        pipeline.load_prices()


def test_a_clean_price_loads(put):
    prices(put, [("A", "1.50")])
    assert pipeline.load_prices() == {"A": (1.5, "d")}


def test_stock_codes_that_differ_only_in_case_are_two_prices(put):
    prices(put, [("85123A", "1.00"), ("85123a", "2.00")])
    assert pipeline.load_prices() == {"85123A": (1.0, "d"), "85123a": (2.0, "d")}


def test_a_two_row_sku_in_descending_order_is_rejected_at_row_3(put):
    demand(put, [("2011-W02", "A", 1), ("2011-W01", "A", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: row 3: weeks for SKU A must be in ascending order, "
            "but 2011-W01 follows 2011-W02")):
        pipeline.load_series()


def test_only_the_second_row_of_a_three_row_sku_out_of_order_is_rejected_at_row_3(put):
    demand(put, [("2011-W02", "A", 1), ("2011-W01", "A", 1), ("2011-W03", "A", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: row 3: weeks for SKU A must be in ascending order, "
            "but 2011-W01 follows 2011-W02")):
        pipeline.load_series()


def test_only_the_third_row_of_a_three_row_sku_out_of_order_is_rejected_at_row_4(put):
    demand(put, [("2011-W02", "A", 1), ("2011-W03", "A", 1), ("2011-W01", "A", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: row 4: weeks for SKU A must be in ascending order, "
            "but 2011-W01 follows 2011-W03")):
        pipeline.load_series()


def test_a_difference_only_in_the_last_week_is_a_different_week_list(put):
    """A: W01 W02 W04, B: W01 W03 W04 share first and last weeks and differ in the middle."""
    demand(put, [("2011-W01", "A", 1), ("2011-W02", "A", 1), ("2011-W04", "A", 1),
                 ("2011-W01", "B", 1), ("2011-W03", "B", 1), ("2011-W04", "B", 1)])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: SKU B covers different weeks than SKU A")):
        pipeline.load_series()
