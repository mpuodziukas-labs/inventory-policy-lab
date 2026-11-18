"""Zero-denominator cases in the error measures, the pipeline and the simulation KPIs."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402
from lab.forecast import mae, wape  # noqa: E402
from lab.rootcause import decompose  # noqa: E402
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
    with pytest.raises(ValueError, match="10000") as err:
        pipeline.run()
    assert isinstance(err.value.__cause__, ValueError)
    assert "WAPE is undefined" in str(err.value.__cause__)


def test_simulation_rejects_a_zero_length_window():
    with pytest.raises(ValueError, match="weeks"):
        simulate([10], 5, 50, [1], [1.0], 1, 0, 0)


def test_simulation_with_zero_demand_raises_no_cycle_error():
    """With no demand the stock never falls to the reorder point, so no order is placed
    and no cycle completes: the fill-rate and turns ratios are never reached."""
    with pytest.raises(ValueError, match="cycle"):
        simulate([0], 5, 50, [1], [1.0], 1, 50, 5)


def test_skewness_of_constant_demand_is_zero_by_convention():
    assert pipeline.skewness([7] * 30) == 0.0
    assert pipeline.skewness([0] * 30) == 0.0


def test_decompose_rejects_zero_total_variance():
    with pytest.raises(ValueError, match="zero"):
        decompose(2, 0, 50, 0)  # constant demand and no lead-time spread
    with pytest.raises(ValueError, match="zero"):
        decompose(2, 0, 0, 0.5)  # constant zero demand


def test_decompose_constant_demand_with_lead_time_spread_is_all_lead_time():
    """sigma_d = 0 alone is not a zero total: the lead-time part carries all the variance."""
    assert decompose(2, 0, 50, 0.5) == (0.0, 1.0)


def test_simulation_rejects_a_negative_window():
    with pytest.raises(ValueError, match="weeks"):
        simulate([10], 5, 50, [1], [1.0], 1, -1, 0)


def test_mae_rejects_empty_actuals_with_forecasts_present():
    with pytest.raises(ValueError, match="no test"):
        mae([], [1, 2, 3])


def test_mae_rejects_a_length_mismatch_either_way():
    with pytest.raises(ValueError, match="length"):
        mae([1, 2, 3], [])
    with pytest.raises(ValueError, match="length"):
        mae([1, 2, 3], [1, 2])
    with pytest.raises(ValueError, match="length"):
        mae([1, 2], [1, 2, 3])


def test_skewness_of_tiny_but_nonzero_spread_is_not_collapsed_to_zero():
    """29 zeros and one 2**-40: spread is far below 1e-9 yet the series is clearly right-skewed.
    Hand-worked: sample sd = e/sqrt(30); the outlier has z = 29/sqrt(30), the rest -1/sqrt(30);
    skewness = (29**3 - 29) / 30**1.5 / 30 = 4.94167..."""
    e = 2.0 ** -40
    got = pipeline.skewness([0.0] * 29 + [e])
    assert got == pytest.approx(29 * 840 / 30 ** 1.5 / 30, rel=1e-9)
    assert got > 0
    assert pipeline.skewness([e] * 29 + [0.0]) < 0


def test_skewness_of_constant_non_integer_demand_is_exactly_zero():
    """statistics.stdev is exact for equal floats, so the zero test is safe for 0.1 and 1/3 too."""
    for v in (0.1, 0.3, 1 / 3, 2.2):
        assert pipeline.skewness([v] * 30) == 0.0


def test_wape_rejects_negative_actuals():
    with pytest.raises(ValueError, match="negative"):
        wape([5, -1, 4], [1, 2, 3])
    with pytest.raises(ValueError, match="negative"):
        wape([-3, 0], [1, 2])  # negative sum
    with pytest.raises(ValueError, match="zero"):
        wape([0, 0], [1, 2])  # zero sum keeps its own error


def test_decompose_rejects_negative_inputs():
    for args in ((-1, 1, 50, 0.5), (2, -1, 50, 0.5), (2, 1, -50, 0.5), (2, 1, 50, -0.5)):
        with pytest.raises(ValueError, match="non-negative"):
            decompose(*args)


def test_wape_checks_negative_before_zero_sum():
    with pytest.raises(ValueError, match="negative"):
        wape([-1, 1], [0, 0])  # sums to zero and holds a negative: the negative error wins


def test_wape_rejects_a_length_mismatch_either_way():
    with pytest.raises(ValueError, match="length"):
        wape([1, 2, 3], [1, 2])
    with pytest.raises(ValueError, match="length"):
        wape([1, 2], [1, 2, 3])


def test_wape_checks_length_before_the_value_checks():
    with pytest.raises(ValueError, match="length"):
        wape([-1, 1], [0])  # negative actual and short forecasts: length is reported
    with pytest.raises(ValueError, match="length"):
        wape([0, 0], [1])  # zero sum and short forecasts: length is reported


def test_decompose_rejects_nan_in_every_position():
    nan = float("nan")
    for args in ((nan, 1, 50, 0.5), (2, nan, 50, 0.5), (2, 1, nan, 0.5), (2, 1, 50, nan)):
        with pytest.raises(ValueError, match="finite"):
            decompose(*args)


def test_decompose_rejects_infinity():
    with pytest.raises(ValueError, match="finite"):
        decompose(float("inf"), 1, 50, 0.5)


def test_decompose_rejects_a_negative_after_a_leading_nan():
    """min() returns the NaN when it comes first, so a later negative used to slip through."""
    with pytest.raises(ValueError):
        decompose(float("nan"), -1, 50, 0.5)


NON_FINITE_PAIRS = (([float("nan"), 1], [1, 1]), ([1, 1], [float("nan"), 1]),
                    ([float("inf"), 1], [1, 1]), ([1, 1], [float("inf"), 1]))


def test_wape_rejects_nan_and_infinity_in_either_list():
    for a, f in NON_FINITE_PAIRS:
        with pytest.raises(ValueError, match="finite"):
            wape(a, f)


def test_mae_rejects_nan_and_infinity_in_either_list():
    for a, f in NON_FINITE_PAIRS:
        with pytest.raises(ValueError, match="finite"):
            mae(a, f)


def test_wape_checks_length_before_the_finite_check():
    with pytest.raises(ValueError, match="length"):
        wape([float("nan"), 1], [1])  # NaN actual and short forecasts: length is reported


def test_mae_checks_length_before_the_finite_check():
    with pytest.raises(ValueError, match="length"):
        mae([float("nan")], [])  # NaN actual and no forecasts: length is reported


def test_mae_checks_empty_before_the_finite_check():
    with pytest.raises(ValueError, match="no test"):
        mae([], [float("nan")])  # empty actuals with a NaN forecast: the empty-window error wins


def _meets_target_at(achieved, tmp_path, monkeypatch):
    """Run the pipeline on one SKU whose simulated cycle service level is `achieved`,
    with target 0.75 and tolerance 0.25 (both exact in binary), so the cutoff is exactly 0.5."""
    (tmp_path / "data").mkdir()
    cfg = json.loads((ROOT / "config.json").read_text())
    cfg.update(service_target=0.75, tolerance=0.25)
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    units = [1 + i % 3 for i in range(52)]
    (tmp_path / "data" / "weekly_demand.csv").write_text(
        "iso_week,stock_code,units\n" + "".join(f"2011-W{i + 1:02d},10000,{u}\n" for i, u in enumerate(units)))
    (tmp_path / "data" / "sku_price.csv").write_text("stock_code,median_unit_price,description\n10000,2.00,item\n")
    stub = lambda *a: {"cycle_service_level": achieved, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
                       "avg_inventory": 1.0, "turns": 1.0, "orders": 1}
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", stub)
    return pipeline.run()["skus"][0]["meets_target"]


def test_meets_target_counts_the_exact_boundary_as_meeting(tmp_path, monkeypatch):
    assert _meets_target_at(0.5, tmp_path, monkeypatch) is True  # achieved == target - tolerance


def test_meets_target_fails_just_below_the_boundary(tmp_path, monkeypatch):
    assert _meets_target_at(0.5 - 2.0 ** -20, tmp_path, monkeypatch) is False
