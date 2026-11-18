"""The pipeline reads its target, review period and error columns from config and the data."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import pipeline  # noqa: E402
from policy.formulas import eoq, safety_stock, z_for_service  # noqa: E402


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


def test_eoq_uses_the_configured_holding_rate(run_with):
    res, _ = run_with(holding_rate_per_year=1.0)
    order_cost = pipeline.load_config()["ordering_cost_per_order"]
    for row in res["skus"]:
        expected = max(1, round(eoq(row["mean_weekly"] * pipeline.WEEKS_PER_YEAR, order_cost, 1.0 * row["price"])))
        assert row["eoq"] == expected


def test_sensitivity_holding_cost_scales_with_the_configured_holding_rate(run_with):
    base, _ = run_with()
    doubled, _ = run_with(holding_rate_per_year=0.5)
    for b, d in zip(base["sensitivity"], doubled["sensitivity"]):
        assert d["safety_stock_units"] == pytest.approx(b["safety_stock_units"])
        assert d["safety_stock_holding_cost"] == pytest.approx(2 * b["safety_stock_holding_cost"])


def test_moving_average_error_uses_the_configured_window(run_with):
    res, _ = run_with(ma_window=8)
    series = pipeline.load_series()
    for row in res["skus"][:3]:
        f_, a_ = fc.rolling_origin(series[row["code"]], lambda h: fc.moving_average(h, 8), 26)
        assert row["mae_ma"] == fc.mae(a_, f_)
        assert row["wape_ma"] == fc.wape(a_, f_)


def test_ses_error_uses_the_configured_alpha(run_with):
    res, _ = run_with(ses_alpha=0.9)
    series = pipeline.load_series()
    for row in res["skus"][:3]:
        f_, a_ = fc.rolling_origin(series[row["code"]], lambda h: fc.ses(h, 0.9), 26)
        assert row["mae_ses"] == fc.mae(a_, f_)
        assert row["wape_ses"] == fc.wape(a_, f_)


def test_eoq_uses_the_configured_ordering_cost(run_with):
    base, _ = run_with()
    res, _ = run_with(ordering_cost_per_order=400.0)
    hold = pipeline.load_config()["holding_rate_per_year"]
    for row in res["skus"]:
        expected = max(1, round(eoq(row["mean_weekly"] * pipeline.WEEKS_PER_YEAR, 400.0, hold * row["price"])))
        assert row["eoq"] == expected
    assert [r["eoq"] for r in res["skus"]] != [r["eoq"] for r in base["skus"]]


def test_simulation_receives_the_configured_weeks_and_warm_up(monkeypatch):
    seen = []

    def spy(history, rop, q, lv, lp, seed, weeks, warmup):
        seen.append((weeks, warmup))
        return _stub_sim(history, rop, q, lv, lp, seed, weeks, warmup)

    cfg = dict(pipeline.load_config(), sim_weeks=777, sim_warmup_weeks=33)
    monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "simulate", spy)
    res = pipeline.run()
    assert seen == [(777, 33)] * res["summary"]["sku_count"]


def test_summary_weeks_is_the_common_series_length(run_with):
    res, _ = run_with()
    lengths = {len(ys) for ys in pipeline.load_series().values()}
    assert len(lengths) == 1
    assert res["summary"]["weeks"] == lengths.pop()


def test_ragged_series_are_rejected_naming_the_sku_and_both_lengths(monkeypatch):
    series = pipeline.load_series()
    first, last = list(series)[0], list(series)[-1]
    series[last] = series[last][:-1]
    n = len(series[first])
    monkeypatch.setattr(pipeline, "load_series", lambda: series)
    monkeypatch.setattr(pipeline, "simulate", _stub_sim)
    with pytest.raises(ValueError) as err:
        pipeline.run()
    msg = str(err.value)
    assert last in msg and str(n - 1) in msg and str(n) in msg


def test_backtest_starts_after_the_configured_minimum_training_weeks(run_with):
    res, _ = run_with(min_train_weeks=30)
    series = pipeline.load_series()
    for row in res["skus"][:3]:
        f_, a_ = fc.rolling_origin(series[row["code"]], fc.naive_forecast, 30)
        assert len(a_) == len(series[row["code"]]) - 30
        assert row["mae_naive"] == fc.mae(a_, f_)


def test_sensitivity_table_lists_the_configured_service_levels(run_with):
    res, _ = run_with(service_levels=[0.80, 0.925, 0.95])
    assert [r["service_level"] for r in res["sensitivity"]] == [0.80, 0.925, 0.95]
    assert [r["z"] for r in res["sensitivity"]] == [z_for_service(0.80), z_for_service(0.925), z_for_service(0.95)]
