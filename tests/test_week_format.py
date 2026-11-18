"""Every iso_week cell must be a year, a dash, W and a two-digit week from 01 to 53, so text order is week order."""
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
def put_demand(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    def write(weeks):
        (tmp_path / "data" / "weekly_demand.csv").write_text(
            "iso_week,stock_code,units\n" + "".join(f"{w},A,1\n" for w in weeks), encoding="utf-8")
    return write


@pytest.mark.parametrize("bad", ["2010-W9", "banana", "2010-W00", "2010-W54", "2010-w01", "2010-W100", "10-W01",
                                 "2010W01", "2010-W01x", "２010-W01", "2010-W٠١"])
def test_a_malformed_week_is_rejected_naming_row_and_cell(put_demand, bad):
    put_demand(["2010-W01", bad])
    with pytest.raises(ValueError, match=exact(
            f"weekly_demand.csv: row 3: iso_week '{bad}' is not a week like 2011-W07 (week 01 to 53)")):
        pipeline.load_series()


def test_the_first_row_is_row_2(put_demand):
    put_demand(["banana"])
    with pytest.raises(ValueError, match=exact(
            "weekly_demand.csv: row 2: iso_week 'banana' is not a week like 2011-W07 (week 01 to 53)")):
        pipeline.load_series()


def test_a_padded_week_is_still_rejected_by_name(put_demand):
    put_demand(["2010-W01", " 2010-W01"])
    with pytest.raises(ValueError, match=exact("weekly_demand.csv: week has surrounding whitespace: ' 2010-W01'")):
        pipeline.load_series()


def test_week_53_and_week_01_are_accepted(put_demand):
    put_demand(["2010-W01", "2010-W09", "2010-W10", "2010-W49", "2010-W50", "2010-W53"])
    assert pipeline.load_series() == {"A": [1, 1, 1, 1, 1, 1]}


def test_weeks_09_then_10_are_ascending(put_demand):
    """Text order only matches week order because every week has two digits."""
    put_demand(["2010-W09", "2010-W10"])
    assert pipeline.load_series() == {"A": [1, 1]}


def format_message(row, cell):
    return f"weekly_demand.csv: row {row}: iso_week '{cell}' is not a week like 2011-W07 (week 01 to 53)"


@pytest.mark.parametrize("bad", ["2010-W60", "2010-W63", "2010-W99", "201-W05", "20100-W05", "201000-W05",
                                 "2010XW05", "2010_W05", "2010-05", "2010--W05", "12010-W05", "x2010-W05", ""])
def test_each_neighbour_shape_of_a_week_is_rejected_with_the_format_error(put_demand, bad):
    put_demand([bad])
    with pytest.raises(ValueError, match=exact(format_message(2, bad))):
        pipeline.load_series()


@pytest.mark.parametrize("good", ["3010-W05", "0999-W05", "0000-W01", "9999-W53"])
def test_any_four_digit_year_is_accepted(put_demand, good):
    put_demand([good])
    assert pipeline.load_series() == {"A": [1]}


@pytest.mark.parametrize("position", [2, 3, 4, 5])
def test_a_bad_week_is_rejected_on_any_row_and_the_message_names_that_row(put_demand, position):
    weeks = [f"2010-W{i + 1:02d}" for i in range(position)] + ["banana"]
    put_demand(weeks)
    with pytest.raises(ValueError, match=exact(format_message(position + 2, "banana"))):
        pipeline.load_series()


def test_a_long_bad_cell_is_quoted_in_full(put_demand):
    put_demand(["2010-W05-extra"])
    with pytest.raises(ValueError, match=exact(format_message(2, "2010-W05-extra"))):
        pipeline.load_series()


DIGITS = "0123456789"


def oracle(s):
    """Independent of the loader and of any regex: eight characters, year, dash, capital W, week 01 to 53."""
    if len(s) != 8:
        return False
    if not all(c in DIGITS for c in s[:4]) or s[4] != "-" or s[5] != "W":
        return False
    if not all(c in DIGITS for c in s[6:]):
        return False
    return 1 <= int(s[6:]) <= 53


def verdict(put_demand, cell):
    put_demand([cell])
    try:
        pipeline.load_series()
    except ValueError:
        return False
    return True


def test_the_oracle_agrees_with_the_documented_examples():
    assert oracle("2010-W05") and oracle("2011-W53") and oracle("2011-W01")
    assert not oracle("2010-W00") and not oracle("2010-W54") and not oracle("2010-w05") and not oracle("2010-W5")


@pytest.mark.parametrize("k", range(100))
def test_every_week_number_from_00_to_99_is_accepted_exactly_from_01_to_53(put_demand, k):
    assert verdict(put_demand, f"2010-W{k:02d}") is (1 <= k <= 53)


BASE = "2010-W05"
DELETIONS = [BASE[:i] + BASE[i + 1:] for i in range(len(BASE))]
SUBSTITUTIONS = [BASE[:i] + c + BASE[i + 1:] for i in range(len(BASE)) for c in "09W-_ x" + "w"]


@pytest.mark.parametrize("cell", DELETIONS + SUBSTITUTIONS)
def test_every_one_character_edit_of_a_valid_week_gets_the_oracle_verdict(put_demand, cell):
    assert verdict(put_demand, cell) is oracle(cell)
