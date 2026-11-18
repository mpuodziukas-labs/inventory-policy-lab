"""A series no longer than the training minimum fails with one named ValueError, whatever its length."""
import json
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


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Build a data folder from (week, code, units) rows and a price file; config.json keys can be overridden."""
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    def build(demand, prices="A,2.50,a\nB,3.00,b\n", **config):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cfg.update(config)
        (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        rows = "".join(f"{w},{c},{u}\n" for w, c, u in demand)
        (tmp_path / "data" / "weekly_demand.csv").write_text("iso_week,stock_code,units\n" + rows)
        (tmp_path / "data" / "sku_price.csv").write_text("stock_code,median_unit_price,description\n" + prices)
        return pipeline.run
    return build


def weeks(n, a=(5,), b=(6,)):
    """n weeks for SKUs A and B; the unit lists repeat to length n."""
    return [(f"2010-W{i + 5:02d}", c, u[i % len(u)]) for i in range(n) for c, u in (("A", a), ("B", b))]


def test_two_weeks_with_a_training_minimum_of_one_complete_with_a_result_for_each_sku(lab):
    run = lab(weeks(2, a=(4, 8), b=(6, 6)), min_train_weeks=1)
    res = run()
    assert [r["code"] for r in res["skus"]] == ["A", "B"]
    a, b = res["skus"]
    assert (a["mae_naive"], a["wape_naive"]) == (4.0, 0.5)
    assert (b["mae_naive"], b["wape_naive"]) == (0.0, 0.0)
    assert res["summary"]["weeks"] == 2


def test_the_short_series_guard_fires_only_below_two_weeks(lab):
    """One week is stopped by the guard (no cause); two or three weeks reach the backtest, whose error names the same window."""
    run = lab(weeks(1))
    with pytest.raises(ValueError) as err:
        run()
    assert (type(err.value), str(err.value), err.value.__cause__) == (ValueError, MESSAGE, None)
    for n in (2, 3):
        run = lab(weeks(n))
        with pytest.raises(ValueError) as err:
            run()
        assert type(err.value) is ValueError and str(err.value) == MESSAGE
        assert type(err.value.__cause__) is ValueError


def test_three_zero_weeks_with_the_default_config_reach_the_eoq_error_not_the_test_window_error(lab):
    run = lab(weeks(3, a=(0,), b=(0,)))
    with pytest.raises(ValueError) as err:
        run()
    assert type(err.value) is ValueError
    assert str(err.value) == "demand, order cost and holding cost must be positive"


def test_a_second_sku_with_fewer_weeks_is_named_by_the_length_error(lab):
    demand = [(f"2010-W{i + 5:02d}", "A", 5) for i in range(3)] + [("2010-W05", "B", 6)]
    with pytest.raises(ValueError) as err:
        lab(demand)()
    assert type(err.value) is ValueError
    assert str(err.value) == "SKU B has 1 weeks but SKU A has 3; every SKU needs the same number of weeks"


def test_a_short_series_with_a_missing_price_reports_the_missing_price(lab):
    with pytest.raises(ValueError) as err:
        lab(weeks(1), prices="A,2.50,a\n")()
    assert type(err.value) is ValueError
    assert str(err.value) == "sku_price.csv: no price row for SKU B"


def test_a_short_series_with_a_bad_price_reports_the_bad_price(lab):
    with pytest.raises(ValueError) as err:
        lab(weeks(1), prices="A,abc,a\nB,3.00,b\n")()
    assert type(err.value) is ValueError
    assert str(err.value) == "sku_price.csv: median_unit_price for SKU A must be a finite number above 0"


def test_a_short_ragged_series_reports_the_length_error_before_the_empty_test_window(lab):
    demand = [("2010-W05", "A", 5), ("2010-W05", "B", 6), ("2010-W06", "B", 6)]
    with pytest.raises(ValueError) as err:
        lab(demand)()
    assert type(err.value) is ValueError
    assert str(err.value) == "SKU B has 2 weeks but SKU A has 1; every SKU needs the same number of weeks"
