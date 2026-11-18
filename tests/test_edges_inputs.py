"""Edge behaviour the SPEC states in Decisions: service level range, negative buffers,
runs with no completed cycle, minimum order size, selftest control, descriptions."""
import csv
import importlib.util
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
