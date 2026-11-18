"""Loader contracts: BOM, padded codes, strict number cells, short rows, check order, explicit encodings."""
import ast
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402

BOM = b"\xef\xbb\xbf"
DEMAND = "weekly_demand.csv"
PRICE = "sku_price.csv"
H_DEMAND = "iso_week,stock_code,units"
H_PRICE = "stock_code,median_unit_price,description"


def _stub_sim(history, rop, q, lv, lp, seed, weeks, warmup):
    return {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
            "avg_inventory": 1.0, "turns": 1.0, "orders": 1}


def exact(text):
    return "^" + re.escape(text) + "$"


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", _stub_sim)
    return tmp_path


def put(d, name, text):
    (d / "data" / name).write_bytes(text.encode("utf-8"))


def demand_rows(code="A", n=52, edit=None):
    rows = [f"2011-W{i + 1:02d},{code},{(i * 7) % 11 + 1}" for i in range(n)]
    for i, row in (edit or {}).items():
        rows[i] = row
    return rows


def files(d, demand=None, price=None):
    put(d, DEMAND, "\n".join([H_DEMAND, *(demand if demand is not None else demand_rows())]) + "\n")
    put(d, PRICE, "\n".join([H_PRICE, *(price if price is not None else ["A,2.50,bag"])]) + "\n")


# ---- BOM and encodings

@pytest.mark.parametrize("which", [(DEMAND,), (PRICE,), (DEMAND, PRICE)])
def test_a_utf8_bom_at_the_start_of_a_data_file_loads_like_the_same_file_without_it(tmp_path, monkeypatch, which):
    plain, bom = tmp_path / "plain", tmp_path / "bom"
    for d in (plain, bom):
        shutil.copytree(ROOT / "data", d / "data")
        shutil.copy(ROOT / "config.json", d / "config.json")
    for name in which:
        f = bom / "data" / name
        f.write_bytes(BOM + f.read_bytes())
    monkeypatch.setattr(pipeline, "simulate", _stub_sim)
    monkeypatch.setattr(pipeline, "ROOT", plain)
    want = pipeline.run()
    monkeypatch.setattr(pipeline, "ROOT", bom)
    assert pipeline.run() == want


def test_a_non_ascii_description_loads_as_utf8(lab_dir):
    files(lab_dir, price=["A,2.50,café ☃"])
    assert pipeline.load_prices()["A"] == (2.5, "café ☃")


def test_a_quoted_description_keeps_an_embedded_windows_newline(lab_dir):
    files(lab_dir, price=['A,2.50,"two\r\nlines"'])
    assert pipeline.load_prices()["A"][1] == "two\r\nlines"


def test_regen_keeps_a_non_ascii_readme_byte_identical_outside_the_block(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    top, bottom = "café ☃ top\n", "bottom éè\n"
    (tmp_path / "README.md").write_bytes(f"{top}{regen.START}\nold\n{regen.END}\n{bottom}".encode("utf-8"))
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", _stub_sim)
    regen.main()
    got = (tmp_path / "README.md").read_bytes()
    assert got.startswith(f"{top}{regen.START}\n".encode("utf-8"))
    assert got.endswith(f"{regen.END}\n{bottom}".encode("utf-8"))


def test_every_file_open_in_regen_and_pipeline_names_its_encoding():
    seen = 0
    for rel in ("lab/regen.py", "lab/pipeline.py"):
        for node in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("open", "read_text", "write_text"):
                seen += 1
                assert "encoding" in {k.arg for k in node.keywords}, f"{rel}:{node.lineno} {name} has no encoding"
    assert seen >= 4


# ---- marker check runs before any data is loaded

def test_regen_checks_the_readme_markers_before_it_runs_the_pipeline(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("no markers here\n", encoding="utf-8")
    monkeypatch.setattr(regen, "ROOT", tmp_path)

    def boom():
        raise RuntimeError("pipeline ran")

    monkeypatch.setattr(regen.pipeline, "run", boom)
    with pytest.raises(SystemExit, match="README markers missing"):
        regen.main()


# ---- header, empty files

def test_an_empty_demand_file_is_a_value_error_naming_the_file(lab_dir):
    files(lab_dir)
    put(lab_dir, DEMAND, "")
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: missing column iso_week")):
        pipeline.run()


def test_an_empty_price_file_is_a_value_error_naming_the_file(lab_dir):
    files(lab_dir)
    put(lab_dir, PRICE, "")
    with pytest.raises(ValueError, match=exact("sku_price.csv: missing column stock_code")):
        pipeline.run()


# ---- surrounding whitespace is a different code, so it is rejected

@pytest.mark.parametrize("raw", [" A", "A ", "\tA", "A "])
def test_a_padded_stock_code_in_the_demand_file_is_rejected(lab_dir, raw):
    files(lab_dir, demand=demand_rows(edit={3: f"2011-W04,{raw},5"}))
    with pytest.raises(ValueError, match=exact(f"weekly_demand.csv: stock code has surrounding whitespace: '{raw}'")):
        pipeline.run()


@pytest.mark.parametrize("raw", [" 2011-W04", "2011-W04 ", "\t2011-W04"])
def test_a_padded_week_in_the_demand_file_is_rejected(lab_dir, raw):
    files(lab_dir, demand=demand_rows(edit={3: f"{raw},A,5"}))
    with pytest.raises(ValueError, match=exact(f"weekly_demand.csv: week has surrounding whitespace: '{raw}'")):
        pipeline.run()


@pytest.mark.parametrize("raw", [" A", "A ", "\tA"])
def test_a_padded_stock_code_in_the_price_file_is_rejected(lab_dir, raw):
    files(lab_dir, price=[f"{raw},2.50,bag"])
    with pytest.raises(ValueError, match=exact(f"sku_price.csv: stock code has surrounding whitespace: '{raw}'")):
        pipeline.run()


def test_a_padded_code_is_not_matched_to_the_unpadded_one_it_is_rejected_first(lab_dir):
    files(lab_dir, demand=demand_rows(code=" A"), price=["A,2.50,bag"])
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: stock code has surrounding whitespace: ' A'")):
        pipeline.run()


def test_whitespace_inside_a_code_is_kept(lab_dir):
    files(lab_dir, demand=demand_rows(code="A B"), price=["A B,2.50,bag"])
    assert list(pipeline.load_series()) == ["A B"]


def test_a_padded_stock_code_is_reported_before_its_bad_units_and_the_code_before_the_week(lab_dir):
    files(lab_dir, demand=demand_rows(edit={3: "2011-W04, A,x"}))
    with pytest.raises(ValueError, match="stock code has surrounding whitespace"):
        pipeline.run()
    files(lab_dir, demand=demand_rows(edit={3: " 2011-W04, A,5"}))
    with pytest.raises(ValueError, match="stock code has surrounding whitespace"):
        pipeline.run()


# ---- strict number cells

@pytest.mark.parametrize("cell", ["1_0", "٣", "５", "+5", "-0", " 5", "5 ", "0x5", "5.0"])
def test_a_units_cell_must_be_ascii_digits_only(lab_dir, cell):
    files(lab_dir, demand=demand_rows(edit={1: f'2011-W02,A,"{cell}"'}))
    msg = "weekly_demand.csv: units for SKU A in week 2011-W02 must be a whole number of at least 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


@pytest.mark.parametrize("cell, want", [("0", 0), ("007", 7), ("12", 12)])
def test_ascii_digit_units_cells_are_accepted(lab_dir, cell, want):
    files(lab_dir, demand=demand_rows(edit={1: f"2011-W02,A,{cell}"}))
    assert pipeline.load_series()["A"][1] == want


@pytest.mark.parametrize("cell", ["2_5", "1_000.5", "٢.5", "２.5"])
def test_a_price_cell_must_be_ascii_without_underscores(lab_dir, cell):
    files(lab_dir, price=[f'A,"{cell}",bag'])
    msg = "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


@pytest.mark.parametrize("cell, want", [("2.50", 2.5), ("1e1", 10.0)])
def test_ordinary_price_cells_are_still_accepted(lab_dir, cell, want):
    files(lab_dir, price=[f'A,"{cell}",bag'])
    assert pipeline.load_prices()["A"][0] == want


# ---- short and malformed rows give one ValueError naming the file

def test_a_price_row_with_no_price_and_no_description_names_the_price_problem(lab_dir):
    files(lab_dir, price=["A"])
    msg = "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


def test_a_price_row_with_no_description_cell_is_rejected_not_passed_to_the_renderer(lab_dir):
    files(lab_dir, price=["A,2.50"])
    with pytest.raises(ValueError, match=exact("sku_price.csv: description missing for SKU A")):
        pipeline.run()


def test_a_price_row_with_an_empty_description_is_still_accepted(lab_dir):
    files(lab_dir, price=["A,2.50,"])
    assert pipeline.load_prices()["A"] == (2.5, "")


def test_a_price_row_with_no_stock_code_cell_is_rejected(lab_dir):
    files(lab_dir)
    put(lab_dir, PRICE, "median_unit_price,description,stock_code\n2.50,bag\n")
    with pytest.raises(ValueError, match=exact("sku_price.csv: a row is missing its stock code")):
        pipeline.run()


@pytest.mark.parametrize("short", ["4", "4,2011-W53"])
def test_a_demand_row_with_no_stock_code_or_week_cell_is_rejected(lab_dir, short):
    put(lab_dir, DEMAND, "units,iso_week,stock_code\n" + "\n".join(
        f"{(i * 7) % 11 + 1},2011-W{i + 1:02d},A" for i in range(52)) + f"\n{short}\n")
    put(lab_dir, PRICE, f"{H_PRICE}\nA,2.50,bag\n")
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: a row is missing its stock code or week")):
        pipeline.run()


# ---- order of the checks

def test_the_demand_file_is_loaded_before_the_price_file(lab_dir):
    put(lab_dir, DEMAND, "iso_week,stock_code\n")
    put(lab_dir, PRICE, "stock_code,description\n")
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: missing column units")):
        pipeline.run()


def test_a_duplicate_row_is_reported_before_its_bad_units(lab_dir):
    files(lab_dir, demand=demand_rows(edit={3: "2011-W01,A,x"}))
    msg = "weekly_demand.csv: duplicate row for SKU A in week 2011-W01"
    with pytest.raises(ValueError, match=exact(msg)):
        pipeline.run()


def test_ragged_series_are_reported_before_a_missing_price(lab_dir):
    files(lab_dir, demand=demand_rows("A", 52) + demand_rows("B", 51), price=["A,2.50,bag"])
    with pytest.raises(ValueError, match="SKU B has 51 weeks but SKU A has 52"):
        pipeline.run()


def test_a_demand_row_with_a_code_but_no_week_cell_is_rejected(lab_dir):
    put(lab_dir, DEMAND, "units,stock_code,iso_week\n" + "\n".join(
        f"{(i * 7) % 11 + 1},A,2011-W{i + 1:02d}" for i in range(52)) + "\n4,A\n")
    put(lab_dir, PRICE, f"{H_PRICE}\nA,2.50,bag\n")
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: a row is missing its stock code or week")):
        pipeline.run()
