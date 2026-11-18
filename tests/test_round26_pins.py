"""Named eoq errors, non-finite order quantity, non-finite variance total, and six pins."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast, pipeline, render  # noqa: E402
from lab.rootcause import decompose  # noqa: E402
from policy.formulas import eoq, z_for_service  # noqa: E402


@pytest.fixture
def lab(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    def build(demand, prices="A,2.50,a\nB,3.00,b\n", **config):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cfg.update(config)
        (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        rows = "".join(f"{w},{c},{u}\n" for w, c, u in demand)
        (tmp_path / "data" / "weekly_demand.csv").write_text("iso_week,stock_code,units\n" + rows)
        (tmp_path / "data" / "sku_price.csv").write_text("stock_code,median_unit_price,description\n" + prices)
        return pipeline.run
    return build


def weeks(n, a=(5,), b=(6,)):
    return [(f"2010-W{i + 5:02d}", c, u[i % len(u)]) for i in range(n) for c, u in (("A", a), ("B", b))]


def test_zero_demand_in_every_week_keeps_its_message(lab):
    with pytest.raises(ValueError) as err:
        lab(weeks(30, a=(5,), b=(0,)))()
    assert str(err.value) == "SKU B has no demand in any week: demand, order cost and holding cost must be positive"


def test_another_eoq_error_keeps_the_sku_and_the_original_message(lab, monkeypatch):
    def bad(*a):
        raise ValueError("odd")
    monkeypatch.setattr(pipeline, "eoq", bad)
    with pytest.raises(ValueError) as err:
        lab(weeks(30))()
    assert type(err.value) is ValueError
    assert str(err.value) == "SKU A: odd"
    assert str(err.value.__cause__) == "odd"


def test_a_non_value_error_inside_eoq_is_not_relabelled(lab, monkeypatch):
    def bad(*a):
        raise RuntimeError("kaput")
    monkeypatch.setattr(pipeline, "eoq", bad)
    with pytest.raises(RuntimeError, match="kaput"):
        lab(weeks(30))()


def test_an_overflow_error_inside_eoq_is_not_relabelled(lab, monkeypatch):
    def bad(*a):
        raise OverflowError("big")
    monkeypatch.setattr(pipeline, "eoq", bad)
    with pytest.raises(OverflowError, match="big"):
        lab(weeks(30))()


def test_a_huge_order_cost_names_the_sku_and_the_non_finite_quantity(lab):
    with pytest.raises(ValueError) as err:
        lab(weeks(30), ordering_cost_per_order=1e308)()
    assert type(err.value) is ValueError
    assert str(err.value) == "SKU A: order quantity is not finite"


def test_a_huge_price_names_the_sku_and_the_non_finite_quantity(lab):
    with pytest.raises(ValueError) as err:
        lab(weeks(30), prices="A,1e308,a\nB,3.00,b\n", holding_rate_per_year=10)()
    assert type(err.value) is ValueError
    assert str(err.value).startswith("SKU A: ")
    assert not isinstance(err.value, OverflowError)


def test_a_safety_stock_error_surfaces_unchanged(lab):
    def boom(*a):
        raise ValueError("boom")
    with pytest.raises(ValueError) as err:
        lab(weeks(30))(safety_stock_fn=boom)
    assert str(err.value) == "boom"


@pytest.mark.parametrize("args", [(1e200, 1e100, 0, 0), (1e200, 1e100, 1e200, 1e100)])
def test_decompose_rejects_a_non_finite_variance_total(args):
    with pytest.raises(ValueError) as err:
        decompose(*args)
    assert type(err.value) is ValueError
    assert str(err.value) == "variance total is not finite"


@pytest.mark.parametrize("total", [5e-324, 1e-16])
def test_decompose_still_returns_shares_for_tiny_totals(total):
    assert decompose(1.0, math.sqrt(total), 0, 0) == (1.0, 0.0)


def test_decompose_still_rejects_a_zero_total():
    with pytest.raises(ValueError, match="both zero"):
        decompose(1.0, 0, 0, 0)


def test_z_for_service_is_exact_just_above_095():
    assert z_for_service(0.9500000000001) == pytest.approx(1.6448536269524419, abs=1e-13)


def test_eoq_accepts_a_tiny_positive_demand():
    assert eoq(1e-10, 50.0, 0.5) == pytest.approx(0.0001414213562373095, rel=1e-12)


def test_wape_with_a_tiny_positive_actual_sum_is_defined():
    assert forecast.wape([1e-10], [0.0]) == 1.0


def test_one_sku_dot_sits_in_the_middle_of_the_plot():
    res = {"summary": {"target": 0.95},
           "skus": [{"code": "A", "cycle_service_level": 0.9, "meets_target": False}]}
    assert 'cx="378.0"' in render._dot_chart(res)
