"""Edge cases for the one-time extract script, on tiny hand-made rows."""
import csv
import importlib.util
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_extract():
    spec = importlib.util.spec_from_file_location("make_extract_edges", ROOT / "scripts" / "make_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_product_code_allows_at_most_two_letters():
    m = load_extract()
    assert m.is_product_code("12345")
    assert m.is_product_code("12345AB")
    assert not m.is_product_code("12345ABC")
    assert not m.is_product_code("1234")


def test_positive_quantity_on_a_cancellation_invoice_is_not_a_sale():
    m = load_extract()
    dt = datetime(2011, 1, 4, 10)
    rows = [("C100", "10001", 5, dt, 1.0), ("A100", "10001", 3, dt, 1.0)]
    assert m.aggregate(rows) == {("2011-W01", "10001"): 3}


def test_full_weeks_boundaries():
    m = load_extract()
    mon = datetime(2011, 1, 3, 0, 0)
    # data starting exactly Monday 00:00 keeps that week; ending Sunday keeps it too
    assert m.full_weeks(mon, datetime(2011, 1, 16)) == ["2011-W01", "2011-W02"]
    # a last day of Wednesday does not complete the second week
    assert m.full_weeks(mon, datetime(2011, 1, 12)) == ["2011-W01"]
    # data starting Tuesday drops that partial first week
    assert m.full_weeks(datetime(2011, 1, 4), datetime(2011, 1, 16)) == ["2011-W02"]


def test_main_ranks_ties_by_units_and_prices_by_median(tmp_path, monkeypatch):
    m = load_extract()
    d1, d2 = datetime(2011, 1, 4, 10), datetime(2011, 1, 11, 10)
    rows = [
        ("A0", "POST", 1, datetime(2011, 1, 3, 0, 0), 1.0, "post"),
        ("A1", "10001", 1, d1, 1.0, "small seller"),
        ("A2", "10001", 1, d2, 1.0, "small seller"),
        ("A3", "10002", 10, d1, 1.0, "big seller"),
        ("A4", "10002", 5, d1, 9.0, "big seller"),
        ("A5", "10002", 5, d2, 2.0, "big seller"),
        ("A6", "POST", 1, datetime(2011, 1, 16, 12, 0), 1.0, "post"),
    ]
    monkeypatch.setattr(m, "read_rows", lambda path: iter(rows))
    monkeypatch.setattr(m, "TOP_SKUS", 1)
    m.main(["x", "ignored.xlsx", str(tmp_path)])
    with open(tmp_path / "weekly_demand.csv", newline="") as f:
        got = list(csv.DictReader(f))
    assert {r["stock_code"] for r in got} == {"10002"}
    assert [r["units"] for r in got] == ["15", "5"]
    with open(tmp_path / "sku_price.csv", newline="") as f:
        price = list(csv.DictReader(f))
    assert price[0]["median_unit_price"] == "2.00"
