"""A series no longer than the training minimum fails with one named ValueError, whatever its length."""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402

MESSAGE = ("SKU A has an empty test window: MAE is undefined: "
           "no test weeks (the series is no longer than the training minimum)")


@pytest.fixture
def run_with_weeks(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    def go(n):
        rows = "".join(f"2010-W{i + 5:02d},{c},{5 + j}\n" for i in range(n) for j, c in enumerate("AB"))
        (tmp_path / "data" / "weekly_demand.csv").write_text("iso_week,stock_code,units\n" + rows)
        (tmp_path / "data" / "sku_price.csv").write_text(
            "stock_code,median_unit_price,description\nA,2.50,a\nB,3.00,b\n")
        return pipeline.run()
    return go


@pytest.mark.parametrize("n", [1, 2, 3])
def test_a_series_of_one_two_or_three_weeks_raises_the_empty_test_window_error(run_with_weeks, n):
    with pytest.raises(ValueError) as err:
        run_with_weeks(n)
    assert type(err.value) is ValueError
    assert str(err.value) == MESSAGE
