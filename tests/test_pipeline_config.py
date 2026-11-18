"""The pipeline reads its target, review period and error columns from config and the data."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import pipeline  # noqa: E402
from policy.formulas import safety_stock, z_for_service  # noqa: E402


def _stub_sim(history, rop, q, lv, lp, seed, weeks, warmup):
    return {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
            "avg_inventory": 1.0, "turns": 1.0, "orders": 1}


@pytest.fixture
def run_with(monkeypatch):
    def go(**overrides):
        cfg = dict(pipeline.load_config(), **overrides)
        calls = []

        def spy(z, lead_time, sigma_d, mean_d, sigma_l):
            calls.append((z, lead_time))
            return safety_stock(z, lead_time, sigma_d, mean_d, sigma_l)

        monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
        monkeypatch.setattr(pipeline, "simulate", _stub_sim)
        res = pipeline.run(safety_stock_fn=spy)
        return res, calls
    return go


def test_base_safety_factor_comes_from_the_config_target(run_with):
    res, calls = run_with(service_target=0.99)
    n = res["summary"]["sku_count"]
    assert {z for z, _ in calls[:n]} == {z_for_service(0.99)}
    assert z_for_service(0.99) != z_for_service(0.95)


def test_protection_interval_adds_the_configured_review_period(run_with):
    res, calls = run_with(review_period_weeks=3)
    lead_mean = 1 * 0.125 + 2 * 0.75 + 3 * 0.125
    assert res["summary"]["protect"] == lead_mean + 3
    assert {lt for _, lt in calls} == {lead_mean + 3}
    row = res["skus"][0]
    assert row["reorder_point"] == pytest.approx(row["mean_weekly"] * (lead_mean + 3) + row["safety_stock"])


def test_each_sku_row_carries_its_mae_per_method(run_with):
    res, _ = run_with()
    series = pipeline.load_series()
    methods = {"naive": fc.naive_forecast, "ma": lambda h: fc.moving_average(h, 4), "ses": lambda h: fc.ses(h, 0.3)}
    for row in res["skus"][:3]:
        for name, fn in methods.items():
            f_, a_ = fc.rolling_origin(series[row["code"]], fn, 26)
            assert row[f"mae_{name}"] == fc.mae(a_, f_)
