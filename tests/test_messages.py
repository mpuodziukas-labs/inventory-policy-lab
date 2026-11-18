"""Error messages are matched by their key words, so a reworded message is a visible change."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import pipeline  # noqa: E402
from policy.formulas import eoq  # noqa: E402
from policy.simulate import simulate  # noqa: E402


def test_simulate_rejects_non_positive_weeks_saying_weeks_must_be_positive():
    with pytest.raises(ValueError, match=r"weeks must be positive"):
        simulate([1], 0, 1, [1], [1.0], 1, 0, 0)


def test_simulate_without_completed_cycles_tells_the_user_to_lengthen():
    with pytest.raises(ValueError, match=r"no completed order cycles; lengthen the simulation"):
        simulate([0], 0, 1, [1], [1.0], 1, 3, 0)


@pytest.mark.parametrize("args", [(0, 50, 1), (100, 0, 1), (100, 50, 0)])
def test_eoq_error_names_all_three_inputs_and_positive(args):
    with pytest.raises(ValueError, match=r"demand, order cost and holding cost must be positive"):
        eoq(*args)


def test_wape_zero_sum_message_says_the_actuals_sum_to_zero():
    with pytest.raises(ValueError, match=r"WAPE is undefined: the actuals sum to zero"):
        fc.wape([0, 0], [1, 1])


def test_wape_length_mismatch_names_the_actual_count_then_the_forecast_count():
    with pytest.raises(ValueError, match=r"WAPE is undefined: 3 actuals but 2 forecasts"):
        fc.wape([1, 2, 3], [1, 2])


def test_mae_length_mismatch_names_the_actual_count_then_the_forecast_count():
    with pytest.raises(ValueError, match=r"MAE is undefined: 3 actuals but 2 forecasts"):
        fc.mae([1, 2, 3], [1, 2])


def test_moving_average_requires_its_window_argument():
    with pytest.raises(TypeError):
        fc.moving_average([1, 2, 3])


def test_pipeline_error_for_a_sku_without_test_demand_carries_the_reason(monkeypatch):
    units = [3] + [0] * 10 + [2] + [0] * 40
    stub = lambda *a: {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
                       "avg_inventory": 1.0, "turns": 1.0, "orders": 1}
    monkeypatch.setattr(pipeline, "load_series", lambda: {"10000": units})
    monkeypatch.setattr(pipeline, "load_prices", lambda: {"10000": (2.0, "item")})
    monkeypatch.setattr(pipeline, "simulate", stub)
    with pytest.raises(ValueError, match=r"SKU 10000 has no demand in its test window: WAPE is undefined"):
        pipeline.run()
