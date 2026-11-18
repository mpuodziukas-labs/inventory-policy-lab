"""Hand-worked pipeline numbers on two tiny SKUs, simulation stubbed out.

SKU 10000: weekly demand 13, 13, 13, 13, price 4.00, so holding cost per unit-year h = 0.25 * 4 = 1.
SKU 10001: weekly demand 12, 14, 12, 14, price 16.00, so h = 0.25 * 16 = 4.
Both have mean 13, so D = 13 * 52 = 676 a year. Order cost S = 50.
EOQ = sqrt(2 * 676 * 50 / h): 10000 gives sqrt(67600) = 260, 10001 gives sqrt(16900) = 130.
Cycle stock cost = h * EOQ / 2: 1 * 130 + 4 * 65 = 390 for the pair.
"""
import json
import sys
from pathlib import Path
from statistics import NormalDist

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402

STUB = lambda *a: {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
                   "avg_inventory": 1.0, "turns": 1.0, "orders": 1}
SERIES = {"10000": [13, 13, 13, 13], "10001": [12, 14, 12, 14]}
PRICES = {"10000": 4.0, "10001": 16.0}


@pytest.fixture
def build(tmp_path, monkeypatch):
    def make(**overrides):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cfg.update({"min_train_weeks": 2, **overrides})
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        (tmp_path / "data" / "weekly_demand.csv").write_text(
            "iso_week,stock_code,units\n"
            + "".join(f"2011-W{i + 1:02d},{code},{u}\n" for code, ys in SERIES.items() for i, u in enumerate(ys)))
        (tmp_path / "data" / "sku_price.csv").write_text(
            "stock_code,median_unit_price,description\n"
            + "".join(f"{code},{p:.2f},item {code}\n" for code, p in PRICES.items()))
        monkeypatch.setattr(pipeline, "ROOT", tmp_path)
        monkeypatch.setattr(pipeline, "simulate", STUB)
    return make


def two_step(z, protect, sd, mean_d, sigma_l):
    """Injected safety stock: one weekly mean for z below 1.7 (levels 0.90 and 0.95), two for the rest."""
    return mean_d * (1 if z < 1.7 else 2)


def test_sensitivity_table_hand_worked_with_an_injected_safety_stock_in_config_order(build):
    levels = [0.99, 0.975, 0.95, 0.9]
    build(service_levels=levels)
    res = pipeline.run(safety_stock_fn=two_step)
    # level: (units, safety stock cost, total cost); units = 13 + 13 or 26 + 26,
    # safety cost = 1 * s_a + 4 * s_b, total = safety cost + 390.
    want = {0.99: (52.0, 130.0, 520.0), 0.975: (52.0, 130.0, 520.0),
            0.95: (26.0, 65.0, 455.0), 0.9: (26.0, 65.0, 455.0)}
    got = res["sensitivity"]
    assert [r["service_level"] for r in got] == levels
    for r in got:
        assert (r["safety_stock_units"], r["safety_stock_holding_cost"], r["total_holding_cost"]) == want[r["service_level"]]
        assert r["z"] == NormalDist().inv_cdf(r["service_level"])
    assert [r["eoq"] for r in res["skus"]] == [260, 130]


def test_sensitivity_uses_the_injected_function_for_every_sku_and_level(build):
    build()
    res = pipeline.run(safety_stock_fn=lambda *a: 1.0)
    assert [r["safety_stock_units"] for r in res["sensitivity"]] == [2.0] * 4


def test_sensitivity_sums_are_not_clipped_at_zero(build):
    """A negative buffer is legal (SPEC: z is not clamped); the table keeps it: -1 for each SKU,
    cost -(1 + 4) = -5, total -5 + 390 = 385."""
    build()
    res = pipeline.run(safety_stock_fn=lambda *a: -1.0)
    for r in res["sensitivity"]:
        assert (r["safety_stock_units"], r["safety_stock_holding_cost"], r["total_holding_cost"]) == (-2.0, -5.0, 385.0)


def test_overall_wape_hand_worked(build):
    """Test weeks 3 and 4 of each SKU (min_train_weeks 2). SKU 10000 is constant, every forecast is exact.
    SKU 10001 actuals 12, 14:
      naive forecasts 14, 12: errors 2 + 2 = 4
      moving average (window 4) forecasts 13, 38/3: errors 1 + 4/3 = 7/3
      smoothing (alpha 0.3) forecasts 12.6, 12.42: errors 0.6 + 1.58 = 2.18
    Sum of actuals over both SKUs: 26 + 26 = 52. Overall WAPE = total error / 52."""
    build()
    w = pipeline.run()["summary"]["wape"]
    assert w["naive"] == pytest.approx(4 / 52)
    assert w["ma"] == pytest.approx(7 / 3 / 52)
    assert w["ses"] == pytest.approx(2.18 / 52)


def test_per_sku_mae_and_wape_hand_worked(build):
    build()
    a, b = pipeline.run()["skus"]
    assert (a["mae_naive"], a["mae_ma"], a["mae_ses"]) == (0.0, 0.0, 0.0)
    assert b["mae_naive"] == pytest.approx(2.0)
    assert b["mae_ma"] == pytest.approx(7 / 6)
    assert b["mae_ses"] == pytest.approx(1.09)
    assert b["wape_naive"] == pytest.approx(4 / 26)


def test_a_sku_with_an_empty_test_window_is_named(build):
    """min_train_weeks equal to the series length leaves no test week: the MAE error must name the SKU."""
    build(min_train_weeks=4)
    with pytest.raises(ValueError, match=r"^SKU 10000 has an empty test window: MAE is undefined") as err:
        pipeline.run()
    assert isinstance(err.value.__cause__, ValueError)
