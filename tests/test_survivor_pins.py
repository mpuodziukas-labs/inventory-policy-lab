"""Pins from the round 17 mutation review: last-bit floats, accumulator types, truthiness, import order."""
import os
import json
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast, pipeline  # noqa: E402
from policy.simulate import simulate  # noqa: E402


FAKE_SIM = {"cycle_service_level": 0.9, "fill_rate": 0.9, "stockout_weeks_per_year": 1.0,
            "avg_inventory": 1.0, "turns": 1.0, "orders": 1}


def test_the_stockout_rate_divides_before_it_multiplies():
    """15 short weeks of 52: 15 / 52 * 52 is 14.999999999999998, 15 * 52 / 52 is 15.0."""
    r = simulate([0, 10], 5, 10, [1], [1.0], 331, 52, 0)
    assert r["stockout_weeks_per_year"] == 14.999999999999998
    assert r["stockout_weeks_per_year"] == 15 / 52 * 52


def test_sensitivity_units_stay_a_float_when_the_safety_stock_function_returns_whole_numbers():
    res = pipeline.run(safety_stock_fn=lambda z, lead_time, sigma_d, mean_d, sigma_l: 0)
    for row in res["sensitivity"]:
        assert type(row["safety_stock_units"]) is float
        assert row["safety_stock_units"] == 0.0


def test_the_mean_service_level_is_the_exactly_rounded_mean(monkeypatch):
    values = [round(random.Random(7).random() * k % 1, 3) for k in range(1, 41)]
    exact = float(sum(Fraction(v) for v in values) / len(values))
    assert sum(values) / len(values) != exact  # the case would be vacuous if both formulas agreed
    feed = iter(values)

    def fake(*args):
        return {**FAKE_SIM, "cycle_service_level": next(feed)}
    monkeypatch.setattr(pipeline, "simulate", fake)
    res = pipeline.run()
    assert res["summary"]["sku_count"] == len(values)
    assert res["summary"]["mean_service_level"] == exact


def test_error_sums_beyond_two_to_the_53_are_added_exactly_before_they_are_rounded(tmp_path, monkeypatch):
    """Naive error 2**53 + 1 for SKU A and 1 for SKU B: a float accumulator rounds each addend, so WAPE is 1.0."""
    (tmp_path / "data").mkdir()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["min_train_weeks"] = 1
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    big = 2**53 + 1
    (tmp_path / "data" / "weekly_demand.csv").write_text(
        "iso_week,stock_code,units\n"
        f"2010-W05,A,0\n2010-W06,A,{big}\n2010-W05,B,0\n2010-W06,B,1\n")
    (tmp_path / "data" / "sku_price.csv").write_text(
        "stock_code,median_unit_price,description\nA,2.50,a\nB,3.00,b\n")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "simulate", lambda *args: dict(FAKE_SIM))  # the real one never ends on these values
    assert pipeline.run()["summary"]["wape"]["naive"] == 1.0


def test_an_empty_series_is_decided_by_its_length_not_its_truthiness():
    class Odd:
        """Length 0 but truthy: only a length test calls it empty."""
        def __len__(self):
            return 0

        def __bool__(self):
            return True

    with pytest.raises(ValueError) as err:
        forecast.naive_forecast(Odd())
    assert type(err.value) is ValueError
    assert str(err.value) == "series must not be empty"


def test_the_selftest_script_imports_this_repository_before_anything_on_pythonpath(tmp_path):
    decoy = tmp_path / "decoy"
    for pkg in ("policy", "lab"):
        (decoy / pkg).mkdir(parents=True)
        (decoy / pkg / "__init__.py").write_text(f"raise RuntimeError('decoy {pkg} imported')\n")
    env = dict(os.environ, PYTHONPATH=str(decoy))
    p = subprocess.run([sys.executable, str(ROOT / "lab" / "selftest.py")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "correct formula check green: True" in p.stdout.splitlines()
