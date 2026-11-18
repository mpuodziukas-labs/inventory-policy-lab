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
