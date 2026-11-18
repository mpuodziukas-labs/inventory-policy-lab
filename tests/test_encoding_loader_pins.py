"""Encodings of config.json and the README, units and price cell edges, description kept verbatim."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402

START, END = regen.START, regen.END
H_DEMAND = "iso_week,stock_code,units"
H_PRICE = "stock_code,median_unit_price,description"


def exact(text):
    return "^" + re.escape(text) + "$"


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    return tmp_path


def put(d, name, text):
    (d / "data" / name).write_bytes(text.encode("utf-8"))


# ---- config.json encoding

def test_config_string_with_non_ascii_text_is_read_as_utf8(lab_dir):
    note = "café ² ☃"
    cfg = dict(json.loads((lab_dir / "config.json").read_text(encoding="utf-8")), note=note)
    (lab_dir / "config.json").write_bytes(json.dumps(cfg, ensure_ascii=False).encode("utf-8"))
    assert pipeline.load_config()["note"] == note


def test_config_with_an_invalid_utf8_byte_fails_with_a_value_error_naming_the_file(lab_dir):
    (lab_dir / "config.json").write_bytes(b'{"seed": 1, "note": "\xff"}')
    with pytest.raises(ValueError, match=exact("config.json is not valid UTF-8")):
        pipeline.load_config()


# ---- README encoding

def test_readme_with_non_ascii_text_keeps_it_through_regen(tmp_path, monkeypatch):
    head, tail = "café ² top\n", "\nbottom ☃\n"
    readme = tmp_path / "README.md"
    readme.write_bytes(f"{head}{START}\nold\n{END}{tail}".encode("utf-8"))
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    regen.main()
    got = readme.read_bytes().decode("utf-8")
    assert got.startswith(f"{head}{START}\n")
    assert got.endswith(f"{END}{tail}")


def test_readme_with_an_invalid_utf8_byte_fails_with_a_value_error_naming_the_file_and_writes_nothing(
        tmp_path, monkeypatch):
    raw = b"top \xff\n" + f"{START}\nold\n{END}\nbottom\n".encode("utf-8")
    readme = tmp_path / "README.md"
    readme.write_bytes(raw)
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=exact("README.md is not valid UTF-8")):
        regen.main()
    assert readme.read_bytes() == raw
    assert sorted(p.name for p in tmp_path.iterdir()) == ["README.md"]


def test_regen_writes_lf_line_endings_so_a_crlf_readme_is_normalised_once(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_bytes(f"top\r\n{START}\r\nold\r\n{END}\r\nbottom\r\n".encode("utf-8"))
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    regen.main()
    first = readme.read_bytes()
    assert b"\r" not in first
    assert first.startswith(f"top\n{START}\n".encode("utf-8"))
    assert first.endswith(f"{END}\nbottom\n".encode("utf-8"))
    regen.main()
    assert readme.read_bytes() == first


# ---- demand units cell

@pytest.mark.parametrize("cell", ["²", "Ⅷ", "٣", "1²"])
def test_a_units_cell_with_a_non_ascii_numeric_character_is_rejected(lab_dir, cell):
    put(lab_dir, "weekly_demand.csv", f"{H_DEMAND}\n2011-W01,A,{cell}\n")
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: units for SKU A in week 2011-W01 must be a whole number of at least 0")):
        pipeline.load_series()


def test_a_units_cell_longer_than_the_int_digit_limit_gets_the_units_message(lab_dir):
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("no int digit limit in this interpreter")
    put(lab_dir, "weekly_demand.csv", f"{H_DEMAND}\n2011-W01,A,{'9' * (limit + 1)}\n")
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: units for SKU A in week 2011-W01 must be a whole number of at least 0")):
        pipeline.load_series()


# ---- price file

def test_a_padded_code_is_reported_before_a_bad_price(lab_dir):
    put(lab_dir, "sku_price.csv", f"{H_PRICE}\n A,abc,bag\n")
    with pytest.raises(ValueError, match=exact("sku_price.csv: stock code has surrounding whitespace: ' A'")):
        pipeline.load_prices()


def test_a_description_is_kept_verbatim_with_its_leading_and_trailing_spaces(lab_dir):
    put(lab_dir, "sku_price.csv", f'{H_PRICE}\nA,2.50," X "\n')
    assert pipeline.load_prices() == {"A": (2.5, " X ")}
