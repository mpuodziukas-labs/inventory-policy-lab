"""Zero-denominator cases in the error measures, the pipeline and the simulation KPIs."""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402
from lab.forecast import mae, wape  # noqa: E402
from policy.simulate import simulate  # noqa: E402


def test_wape_rejects_all_zero_actuals():
    with pytest.raises(ValueError, match="zero"):
        wape([0, 0, 0], [1, 2, 3])


def test_mae_rejects_empty_test_window():
    with pytest.raises(ValueError, match="no test"):
        mae([], [])


def test_pipeline_names_a_sku_with_no_demand_in_its_test_window(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    units = [3] + [0] * 10 + [2] + [0] * 40
    (tmp_path / "data" / "weekly_demand.csv").write_text(
        "iso_week,stock_code,units\n" + "".join(f"2011-W{i + 1:02d},10000,{u}\n" for i, u in enumerate(units)))
    (tmp_path / "data" / "sku_price.csv").write_text("stock_code,median_unit_price,description\n10000,2.00,item\n")
    stub = lambda *a: {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
                       "avg_inventory": 1.0, "turns": 1.0, "orders": 1}
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", stub)
    with pytest.raises(ValueError, match="10000"):
        pipeline.run()


def test_simulation_rejects_a_zero_length_window():
    with pytest.raises(ValueError, match="weeks"):
        simulate([10], 5, 50, [1], [1.0], 1, 0, 0)


def test_simulation_with_zero_demand_raises_no_cycle_error():
    """With no demand the stock never falls to the reorder point, so no order is placed
    and no cycle completes: the fill-rate and turns ratios are never reached."""
    with pytest.raises(ValueError, match="cycle"):
        simulate([0], 5, 50, [1], [1.0], 1, 50, 5)
