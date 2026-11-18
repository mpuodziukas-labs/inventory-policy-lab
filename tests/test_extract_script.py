"""make_extract on tiny synthetic rows: ranking, cleaning, output order and argument handling."""
import csv
import hashlib
import importlib.util
import shutil
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_extract.py"

MON = datetime(2011, 1, 3, 0, 0)    # first moment of 2011-W01
SUN_NOON = datetime(2011, 1, 16, 12, 0)  # ends 2011-W02, so W01 and W02 are full weeks
W1, W2 = datetime(2011, 1, 4, 10), datetime(2011, 1, 11, 10)


def load(path=SCRIPT, name="make_extract_script"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def span():
    """Service-code rows that stretch the data over two full weeks and are never ranked."""
    return [("S0", "POST", 1, MON, 1.0, "post"), ("S1", "POST", 1, SUN_NOON, 1.0, "post")]


def run_main(m, monkeypatch, rows, argv):
    monkeypatch.setattr(m, "read_rows", lambda path: iter(span() + rows))
    m.main(argv)


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_exactly_forty_skus_are_kept(tmp_path, monkeypatch):
    m = load()
    rows = [(f"A{i}", f"{10001 + i}", 2, W1, 1.0, f"item {i}") for i in range(40)]
    rows.append(("A99", "10041", 1, W1, 1.0, "item 41"))  # weakest, ranks 41st
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    codes = [r["stock_code"] for r in read(tmp_path / "sku_price.csv")]
    assert len(codes) == 40
    assert "10041" not in codes
    assert len({r["stock_code"] for r in read(tmp_path / "weekly_demand.csv")}) == 40


def test_product_code_check_strips_surrounding_whitespace():
    m = load()
    assert m.is_product_code(" 12345 ")
    assert m.is_product_code("12345AB\t")
    dt = datetime(2011, 1, 4, 10)
    assert m.aggregate([("A1", " 10001 ", 2, dt, 1.0)]) == {("2011-W01", "10001"): 2}


def test_zero_quantity_sale_rows_create_no_entry():
    m = load()
    dt = datetime(2011, 1, 4, 10)
    assert m.aggregate([("A1", "10001", 0, dt, 1.0)]) == {}


def test_output_skus_are_listed_in_code_order_not_rank_order(tmp_path, monkeypatch):
    m = load()
    rows = [("A1", "10001", 1, W1, 1.0, "low"), ("A2", "10002", 9, W1, 1.0, "high"),
            ("A3", "10002", 9, W2, 1.0, "high")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    assert [r["stock_code"] for r in read(tmp_path / "sku_price.csv")] == ["10001", "10002"]
    assert [r["stock_code"] for r in read(tmp_path / "weekly_demand.csv")][:2] == ["10001", "10002"]


def test_commas_are_removed_from_descriptions(tmp_path, monkeypatch):
    m = load()
    rows = [("A1", "10001", 1, W1, 1.0, "RED, WHITE MUG")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    lines = (tmp_path / "sku_price.csv").read_text().splitlines()
    assert lines[1] == "10001,1.00,RED  WHITE MUG"


def test_sales_in_partial_weeks_do_not_enter_the_ranking(tmp_path, monkeypatch):
    m = load()
    tue = datetime(2011, 1, 4, 0, 0)
    rows = [
        ("S2", "POST", 1, tue, 1.0, "post"),                    # data starts Tuesday: W01 is partial
        ("A1", "10001", 1, datetime(2011, 1, 12, 10), 1.0, "kept"),
        ("A2", "10002", 100, datetime(2011, 1, 5, 10), 1.0, "partial week only"),
    ]
    monkeypatch.setattr(m, "read_rows", lambda path: iter(rows + [("S3", "POST", 1, SUN_NOON, 1.0, "post")]))
    m.main(["x", "ignored.xlsx", str(tmp_path)])
    assert {r["stock_code"] for r in read(tmp_path / "sku_price.csv")} == {"10001"}


def test_one_argument_writes_to_the_default_data_dir(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "make_extract.py")
    m = load(tmp_path / "scripts" / "make_extract.py", "make_extract_copy")
    run_main(m, monkeypatch, [("A1", "10001", 1, W1, 1.0, "item")], ["x", "ignored.xlsx"])
    assert [r["stock_code"] for r in read(tmp_path / "data" / "sku_price.csv")] == ["10001"]


def test_no_argument_prints_usage_and_exits_non_zero():
    p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode != 0
    assert "Usage: python3 scripts/make_extract.py" in p.stderr


def test_lower_case_suffix_letters_make_a_product_code():
    m = load()
    assert m.is_product_code("12345ab")
    assert m.is_product_code("12345a")
    dt = datetime(2011, 1, 4, 10)
    assert m.aggregate([("A1", "12345a", 2, dt, 1.0)]) == {("2011-W01", "12345a"): 2}


def test_zero_quantity_cancellation_rows_create_no_entry():
    m = load()
    assert m.aggregate([("C1", "10001", 0, datetime(2011, 1, 4, 10), 1.0)]) == {}


def test_integer_invoice_numbers_are_accepted():
    m = load()
    dt = datetime(2011, 1, 4, 10)
    assert m.aggregate([(536365, "10001", 3, dt, 1.0)]) == {("2011-W01", "10001"): 3}


def test_float_quantities_net_to_whole_units():
    m = load()
    dt = datetime(2011, 1, 4, 10)
    net = m.aggregate([("A1", "10001", 6.0, dt, 1.0), ("A2", "10001", 4.0, dt, 1.0)])
    assert net == {("2011-W01", "10001"): 10}
    assert type(net[("2011-W01", "10001")]) is int


def test_first_week_is_dropped_when_data_starts_mid_day_on_a_monday():
    m = load()
    assert m.full_weeks(datetime(2011, 1, 3, 10, 0), SUN_NOON) == ["2011-W02"]


def test_first_week_is_dropped_when_data_starts_a_microsecond_after_monday_midnight():
    m = load()
    assert m.full_weeks(datetime(2011, 1, 3, 0, 0, 0, 1), SUN_NOON) == ["2011-W02"]


def test_week_label_uses_the_iso_year():
    m = load()
    assert m.week_label(datetime(2011, 1, 1)) == "2010-W52"
    assert m.week_label(datetime(2012, 12, 31)) == "2013-W01"


def test_descriptions_are_stripped_before_counting(tmp_path, monkeypatch):
    m = load()
    rows = [("A1", "10001", 1, W1, 1.0, " MUG "), ("A2", "10001", 1, W1, 1.0, "MUG"),
            ("A3", "10001", 1, W1, 1.0, " MUG ")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    assert (tmp_path / "sku_price.csv").read_text().splitlines()[1] == "10001,1.00,MUG"


def test_empty_descriptions_are_not_counted(tmp_path, monkeypatch):
    m = load()
    rows = [("A1", "10001", 1, W1, 1.0, ""), ("A2", "10001", 1, W1, 1.0, ""),
            ("A3", "10001", 1, W1, 1.0, ""), ("A4", "10001", 1, W1, 1.0, "REAL")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    assert (tmp_path / "sku_price.csv").read_text().splitlines()[1] == "10001,1.00,REAL"


def test_a_nested_out_dir_is_created(tmp_path, monkeypatch):
    m = load()
    out = tmp_path / "a" / "b"
    run_main(m, monkeypatch, [("A1", "10001", 1, W1, 1.0, "item")], ["x", "ignored.xlsx", str(out)])
    assert (out / "weekly_demand.csv").exists()
    assert (out / "sku_price.csv").exists()


def test_the_summary_line_names_the_first_and_last_week(tmp_path, monkeypatch, capsys):
    m = load()
    run_main(m, monkeypatch, [("A1", "10001", 1, W1, 1.0, "item")], ["x", "ignored.xlsx", str(tmp_path)])
    assert capsys.readouterr().out.splitlines()[-1] == "weeks 2011-W01 2011-W02 2 skus 1"


def test_the_printed_digests_are_the_sha256_of_the_written_files(tmp_path, monkeypatch, capsys):
    m = load()
    run_main(m, monkeypatch, [("A1", "10001", 1, W1, 1.0, "item")], ["x", "ignored.xlsx", str(tmp_path)])
    printed = dict(line.split() for line in capsys.readouterr().out.splitlines()[:2])
    for name in ("weekly_demand.csv", "sku_price.csv"):
        assert printed[name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()


def test_ranking_is_by_active_weeks_not_by_units(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m, "TOP_SKUS", 1)
    rows = [("A1", "10001", 1, W1, 1.0, "steady"), ("A2", "10001", 1, W2, 1.0, "steady"),
            ("A3", "10002", 100, W1, 1.0, "burst")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    assert [r["stock_code"] for r in read(tmp_path / "sku_price.csv")] == ["10001"]


def test_a_week_that_nets_to_zero_is_not_an_active_week(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m, "TOP_SKUS", 1)
    rows = [("A1", "10001", 5, W1, 1.0, "netted"), ("C1", "10001", -5, W1, 1.0, "netted"),
            ("A2", "10001", 1, W2, 1.0, "netted"),
            ("A3", "10002", 3, W1, 1.0, "one week")]
    run_main(m, monkeypatch, rows, ["x", "ignored.xlsx", str(tmp_path)])
    assert [r["stock_code"] for r in read(tmp_path / "sku_price.csv")] == ["10002"]


def test_a_price_with_pence_is_kept_not_truncated(tmp_path, monkeypatch):
    m = load()
    run_main(m, monkeypatch, [("A1", "10001", 1, W1, 2.55, "item")], ["x", "ignored.xlsx", str(tmp_path)])
    assert (tmp_path / "sku_price.csv").read_text().splitlines()[1] == "10001,2.55,item"


HEADER = ("InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country")
GOOD = ("536365", "85123A", "WHITE HANGING HEART", 6, datetime(2010, 12, 1, 8, 26), 2.55, 17850, "UK")


def fake_workbook(monkeypatch, formula_rows, cached_rows=None):
    """Stand in for openpyxl: data_only=True serves cached values, otherwise the formulas."""
    cached_rows = formula_rows if cached_rows is None else cached_rows

    class Sheet:
        def __init__(self, rows):
            self.rows = rows

        def iter_rows(self, values_only=False):
            assert values_only
            return iter(self.rows)

    class Book:
        def __init__(self, rows):
            self.active = Sheet(rows)

    def load_workbook(path, read_only=False, data_only=False):
        return Book(cached_rows if data_only else formula_rows)

    fake = types.ModuleType("openpyxl")
    fake.load_workbook = load_workbook
    monkeypatch.setitem(sys.modules, "openpyxl", fake)


def test_read_rows_yields_cell_values_not_formulas(monkeypatch):
    m = load()
    formula = GOOD[:3] + ("=2+4",) + GOOD[4:]
    fake_workbook(monkeypatch, [HEADER, formula], [HEADER, GOOD])
    assert list(m.read_rows("book.xlsx"))[0][2] == 6


def test_read_rows_skips_rows_with_no_date_or_no_stock_code(monkeypatch):
    m = load()
    no_date = GOOD[:4] + (None,) + GOOD[5:]
    no_code = GOOD[:1] + (None,) + GOOD[2:]
    fake_workbook(monkeypatch, [HEADER, no_date, no_code, GOOD])
    assert len(list(m.read_rows("book.xlsx"))) == 1


def test_read_rows_maps_columns_by_the_header_row(monkeypatch):
    m = load()
    fake_workbook(monkeypatch, [HEADER, GOOD])
    assert list(m.read_rows("book.xlsx")) == [
        ("536365", "85123A", 6, datetime(2010, 12, 1, 8, 26), 2.55, "WHITE HANGING HEART")]
