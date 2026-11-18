"""Pins for the zero-demand test, the variance total, the reorder point, the shortage flag and the README BOM."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402
from lab.rootcause import decompose  # noqa: E402
from policy.formulas import reorder_point  # noqa: E402
from policy.simulate import simulate  # noqa: E402

TINY_PRICE = "5e-324"  # holding cost underflows to 0, so eoq raises for a reason other than zero demand
OTHER = "SKU A: demand, order cost and holding cost must be positive"


def run_with(tmp_path, monkeypatch, units):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    rows = "".join(f"2010-W{i + 5:02d},A,{u}\n" for i, u in enumerate(units))
    (tmp_path / "data" / "weekly_demand.csv").write_text("iso_week,stock_code,units\n" + rows)
    (tmp_path / "data" / "sku_price.csv").write_text(
        f"stock_code,median_unit_price,description\nA,{TINY_PRICE},a\n")
    with pytest.raises(ValueError) as err:
        pipeline.run()
    return str(err.value)


def test_some_demand_and_one_zero_week_is_not_called_no_demand(tmp_path, monkeypatch):
    assert run_with(tmp_path, monkeypatch, [3] * 14 + [0] + [3] * 15) == OTHER


def test_demand_in_the_first_week_only_is_not_called_no_demand(tmp_path, monkeypatch):
    assert run_with(tmp_path, monkeypatch, [5] + [0] * 29) == OTHER


def test_one_unit_in_thirty_weeks_is_not_called_no_demand(tmp_path, monkeypatch):
    """Whole units only, so a mean below 1 with some demand needs a single unit in a long series."""
    assert run_with(tmp_path, monkeypatch, [0] * 29 + [1]) == OTHER


def test_variance_total_overflow_from_the_lead_part_is_not_finite():
    with pytest.raises(ValueError) as err:
        decompose(1, 0, 1e150, 1e150)
    assert str(err.value) == "variance total is not finite"


def test_reorder_point_is_not_clamped_at_zero():
    assert reorder_point(1, 1, -5) == -4


def test_demand_a_hair_over_stock_is_a_shortage_week():
    out = simulate([10.0000000001], 0, 10.0, [1], [1.0], 1, 52, 4)
    assert out["stockout_weeks_per_year"] == 52.0


def test_regen_keeps_a_byte_order_mark_at_the_start_of_the_readme(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    readme = tmp_path / "README.md"
    readme.write_bytes(b"\xef\xbb\xbf" + f"top\n{regen.START}\nold\n{regen.END}\nbottom\n".encode("utf-8"))
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    regen.main()
    data = readme.read_bytes()
    assert data.startswith(b"\xef\xbb\xbftop\n")
    assert not data.startswith(b"\xef\xbb\xbf\xef\xbb\xbf")
