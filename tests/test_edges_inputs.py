"""Edge behaviour the SPEC states in Decisions: service level range, negative buffers,
runs with no completed cycle, minimum order size, selftest control, descriptions."""
import csv
import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import pipeline, selftest  # noqa: E402
from policy.formulas import reorder_point, safety_stock, z_for_service  # noqa: E402
from policy.simulate import simulate  # noqa: E402


def test_z_is_not_clamped_at_high_service_levels():
    """Standard normal: z(0.9995) = 3.2905."""
    assert abs(z_for_service(0.9995) - 3.2905) < 1e-3


def test_z_rejects_levels_outside_the_open_interval():
    for bad in (0.0, 1.0, -0.1, 1.2):
        with pytest.raises(ValueError):
            z_for_service(bad)


def test_service_below_half_gives_negative_z_and_negative_safety_stock():
    """z(0.4) = -0.2533; L=4, sigma_d=3, d=10, sigma_L=0: sqrt(4*9)=6, so SS = -0.2533*6 = -1.52."""
    z = z_for_service(0.4)
    assert abs(z + 0.2533) < 1e-3
    assert abs(safety_stock(z, 4, 3.0, 10.0, 0.0) + 1.52) < 0.01


def test_reorder_point_keeps_a_negative_safety_stock():
    """d=10, L=2, safety -3: 10*2 + (-3) = 17."""
    assert reorder_point(10, 2, -3) == 17


def test_simulation_with_no_completed_order_cycle_raises():
    """Constant demand 10, lead 1, s=5, Q=50: the first order fires at the end of
    week 5, so a 3-week run completes no cycle."""
    with pytest.raises(ValueError):
        simulate([10], 5, 50, [1], [1.0], 1, 3, 0)


def test_near_zero_demand_still_orders_at_least_one_unit(tmp_path, monkeypatch):
    """Two units in 52 weeks at a very high price give EOQ about 0.03, which rounds to 0."""
    (tmp_path / "data").mkdir()
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    units = [1] + [0] * 38 + [1] + [0] * 12
    (tmp_path / "data" / "weekly_demand.csv").write_text(
        "iso_week,stock_code,units\n" + "".join(f"2011-W{i + 1:02d},10000,{u}\n" for i, u in enumerate(units)))
    (tmp_path / "data" / "sku_price.csv").write_text("stock_code,median_unit_price,description\n10000,1000000.00,rare item\n")
    seen = []

    def stub(history, rop, q, lv, lp, seed, weeks, warmup):
        seen.append(q)
        return {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
                "avg_inventory": 1.0, "turns": 1.0, "orders": 1}

    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", stub)
    pipeline.run()
    assert seen == [1]


def test_selftest_fails_when_the_clean_control_is_red(monkeypatch):
    monkeypatch.setattr(selftest, "service_check", lambda results: False)
    assert selftest.run() == 1


def test_sku_description_is_the_most_common_one(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("make_extract_inputs", ROOT / "scripts" / "make_extract.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    d1, d2, d3 = datetime(2011, 1, 4, 10), datetime(2011, 1, 11, 10), datetime(2011, 1, 12, 10)
    rows = [
        ("A0", "POST", 1, datetime(2011, 1, 3, 0, 0), 1.0, "post"),
        ("A1", "10001", 1, d1, 1.0, "common name"),
        ("A2", "10001", 1, d2, 1.0, "common name"),
        ("A3", "10001", 1, d3, 1.0, "rare name"),
        ("A6", "POST", 1, datetime(2011, 1, 16, 12, 0), 1.0, "post"),
    ]
    monkeypatch.setattr(m, "read_rows", lambda path: iter(rows))
    m.main(["x", "ignored.xlsx", str(tmp_path)])
    with open(tmp_path / "sku_price.csv", newline="") as f:
        assert list(csv.DictReader(f))[0]["description"] == "common name"


def run_child(code, timeout=10):
    """Run code in a child interpreter so a regression into an endless loop fails fast."""
    try:
        return subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.fail(f"still running after {timeout}s: {code!r}")


@pytest.mark.parametrize("qty", [0, -3])
def test_simulate_rejects_a_non_positive_order_quantity_instead_of_looping(qty):
    p = run_child(f"from policy.simulate import simulate\nsimulate([5, 6, 7], 10, {qty}, [1, 2], [0.5, 0.5], 1, 10, 2)\n")
    assert p.returncode != 0
    assert "ValueError: order quantity must be positive" in p.stderr


@pytest.mark.parametrize("leads", [[-1], [0], [1, 0], [1.5], [2.0], [float("nan")], [float("inf")]])
def test_simulate_rejects_lead_values_that_are_not_whole_weeks_of_at_least_one(leads):
    with pytest.raises(ValueError, match=r"lead values must be whole weeks of at least 1"):
        simulate([5, 6, 7], 10, 5, leads, [1.0 / len(leads)] * len(leads), 1, 20, 2)


def test_simulate_rejects_an_empty_history():
    with pytest.raises(ValueError, match=r"history must not be empty"):
        simulate([], 10, 5, [1], [1.0], 1, 20, 2)


@pytest.mark.parametrize("probs", [[0.5, 0.4], [0.6, 0.6], [0.9, 0.9], [float("nan"), 1.0]])
def test_simulate_rejects_lead_probabilities_that_do_not_sum_to_one(probs):
    with pytest.raises(ValueError, match=r"lead probabilities must sum to 1"):
        simulate([5, 6, 7], 10, 5, [1, 2], probs, 1, 20, 2)


def test_simulate_rejects_a_negative_lead_probability_even_when_the_sum_is_one():
    with pytest.raises(ValueError, match=r"lead probabilities cannot be negative"):
        simulate([5, 6, 7], 10, 5, [1, 2], [-0.25, 1.25], 1, 20, 2)


@pytest.mark.parametrize("values, probs", [([1, 2], [1.0]), ([1], [0.5, 0.5])])
def test_simulate_rejects_lead_values_and_probabilities_of_different_length(values, probs):
    with pytest.raises(ValueError, match=r"lead values and probabilities must have the same length"):
        simulate([5, 6, 7], 10, 5, values, probs, 1, 20, 2)


def test_simulate_rejects_empty_lead_lists_because_no_probability_sums_to_one():
    with pytest.raises(ValueError, match=r"lead probabilities must sum to 1"):
        simulate([5, 6, 7], 10, 5, [], [], 1, 20, 2)


def test_simulate_accepts_probabilities_that_sum_to_one_within_the_tolerance():
    simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5 + 5e-10], 1, 50, 2)
    with pytest.raises(ValueError, match=r"lead probabilities must sum to 1"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5 + 2e-9], 1, 50, 2)


@pytest.mark.parametrize("k", [0, -1, -5])
def test_moving_average_rejects_a_window_below_one(k):
    with pytest.raises(ValueError, match=r"moving average window must be at least 1"):
        fc.moving_average([1, 2, 3, 10], k)


def test_moving_average_still_accepts_a_window_of_one():
    assert fc.moving_average([1, 2, 3, 10], 1) == 10


@pytest.mark.parametrize("min_train", [0, -1])
def test_rolling_origin_rejects_a_training_minimum_below_one(min_train):
    with pytest.raises(ValueError, match=r"min_train must be at least 1"):
        fc.rolling_origin([1, 2, 3, 4], fc.naive_forecast, min_train)


def test_rolling_origin_accepts_a_training_minimum_of_one():
    forecasts, actuals = fc.rolling_origin([1, 2, 3], fc.naive_forecast, 1)
    assert forecasts == [1, 2]
    assert actuals == [2, 3]


def test_simulate_accepts_a_zero_probability_lead_value_and_never_uses_it():
    only_two = simulate([5, 6, 7], 10, 20, [2], [1.0], 1, 200, 10)
    with_zero = simulate([5, 6, 7], 10, 20, [1, 2], [0.0, 1.0], 1, 200, 10)
    assert only_two["orders"] > 0
    assert with_zero == only_two


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1, -0.5])
def test_simulate_rejects_history_values_that_are_not_finite_or_are_negative(bad):
    with pytest.raises(ValueError, match=r"history values must be finite and not negative"):
        simulate([5, bad, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 20, 2)


def test_simulate_accepts_zero_demand_weeks_in_the_history():
    simulate([0, 6, 0, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 50, 2)


def test_simulate_rejects_a_negative_warm_up():
    with pytest.raises(ValueError, match=r"warmup must not be negative"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 20, -1)


def test_simulate_accepts_a_warm_up_of_zero():
    simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 50, 0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_simulate_rejects_a_bad_value_in_the_first_history_position(bad):
    with pytest.raises(ValueError, match=r"history values must be finite and not negative"):
        simulate([bad, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 20, 2)


@pytest.mark.parametrize("rop", [float("inf"), float("-inf"), float("nan"), -1])
def test_simulate_rejects_a_reorder_point_that_is_not_finite_or_is_negative(rop):
    p = run_child(f"from policy.simulate import simulate\nsimulate([5, 6, 7], float('{rop}'), 5, [1, 2], [0.5, 0.5], 1, 20, 2)\n")
    assert p.returncode != 0
    assert "ValueError: reorder point must be finite and not negative" in p.stderr


def test_simulate_accepts_a_reorder_point_of_zero():
    simulate([5, 6, 7], 0, 5, [1, 2], [0.5, 0.5], 1, 50, 2)


@pytest.mark.parametrize("warmup", [2.0, 2.5, float("nan"), True])
def test_simulate_rejects_a_warm_up_that_is_not_a_whole_number(warmup):
    with pytest.raises(ValueError, match=r"warmup must be a whole number"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 20, warmup)


@pytest.mark.parametrize("qty", [float("inf"), float("nan")])
def test_simulate_rejects_an_order_quantity_that_is_not_finite(qty):
    with pytest.raises(ValueError, match=r"order quantity must be positive and finite"):
        simulate([5, 6, 7], 10, qty, [1, 2], [0.5, 0.5], 1, 20, 2)


def test_simulate_reports_a_negative_fractional_window_as_not_whole_before_not_positive():
    with pytest.raises(ValueError, match=r"weeks must be a whole number"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, -1.5, 2)


def test_simulate_reports_the_window_before_the_warm_up():
    with pytest.raises(ValueError, match=r"weeks must be positive"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 0, -1)
    with pytest.raises(ValueError, match=r"weeks must be positive"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 0, 1.5)


def test_simulate_reports_history_values_before_the_reorder_point_and_the_order_quantity():
    with pytest.raises(ValueError, match=r"history values must be finite and not negative"):
        simulate([-1], -1, 0, [1], [1.0], 1, 20, 2)


def test_simulate_reports_the_reorder_point_before_the_order_quantity():
    with pytest.raises(ValueError, match=r"reorder point must be finite and not negative"):
        simulate([5, 6, 7], -1, 0, [1], [1.0], 1, 20, 2)


def test_simulate_reports_the_order_quantity_before_the_lead_values():
    with pytest.raises(ValueError, match=r"order quantity must be positive"):
        simulate([5, 6, 7], 10, 0, [0], [1.0], 1, 20, 2)


def test_simulate_reports_bad_lead_values_before_a_length_mismatch():
    with pytest.raises(ValueError, match=r"lead values must be whole weeks of at least 1"):
        simulate([5, 6, 7], 10, 5, [0], [0.5, 0.5], 1, 20, 2)


def test_moving_average_reports_the_window_before_the_empty_series():
    with pytest.raises(ValueError, match=r"moving average window must be at least 1"):
        fc.moving_average([], 0)


def test_wape_reports_non_finite_input_before_a_negative_actual():
    with pytest.raises(ValueError, match=r"finite"):
        fc.wape([-1, float("nan")], [0, 0])


@pytest.mark.parametrize("weeks", [20.0, 20.5, True])
def test_simulate_rejects_a_window_that_is_not_a_whole_number(weeks):
    with pytest.raises(ValueError, match=r"weeks must be a whole number"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, weeks, 2)


def test_simulate_rejects_a_boolean_lead_value():
    with pytest.raises(ValueError, match=r"lead values must be whole weeks of at least 1"):
        simulate([5, 6, 7], 10, 5, [True], [1.0], 1, 20, 2)


@pytest.mark.parametrize("name, call", [
    ("naive_forecast", lambda: fc.naive_forecast([])),
    ("moving_average", lambda: fc.moving_average([], 4)),
    ("ses", lambda: fc.ses([], 0.3)),
])
def test_forecast_methods_reject_an_empty_series_with_one_message(name, call):
    with pytest.raises(ValueError, match=r"series must not be empty"):
        call()


def test_forecast_methods_still_accept_a_series_of_one_week():
    assert fc.naive_forecast([4]) == 4
    assert fc.moving_average([4], 4) == 4
    assert fc.ses([4], 0.3) == 4
