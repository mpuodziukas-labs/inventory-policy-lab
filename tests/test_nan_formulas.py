"""NaN and infinity are rejected by name in every formula, never returned as a number."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from policy.formulas import eoq, reorder_point, safety_stock, z_for_service  # noqa: E402

NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_z_for_service_rejects_non_finite_levels(bad):
    with pytest.raises(ValueError):
        z_for_service(bad)


@pytest.mark.parametrize("args", [(NAN, 50, 1), (INF, 50, 1), (5, NAN, 1), (5, 5, NAN), (5, INF, 1), (5, 5, INF)])
def test_eoq_rejects_non_finite_inputs(args):
    with pytest.raises(ValueError):
        eoq(*args)


@pytest.mark.parametrize("args", [(NAN, 2, 1, 1, 1), (1, NAN, 1, 1, 1), (1, 2, NAN, 1, 1), (1, 2, 1, NAN, 1),
                                  (1, 2, 1, 1, NAN), (INF, 2, 1, 1, 1)])
def test_safety_stock_rejects_non_finite_inputs(args):
    with pytest.raises(ValueError):
        safety_stock(*args)


@pytest.mark.parametrize("args", [(NAN, 2, 1), (1, NAN, 1), (1, 2, NAN), (INF, 2, 1)])
def test_reorder_point_rejects_non_finite_inputs(args):
    with pytest.raises(ValueError):
        reorder_point(*args)


def _bad_in_each_position(fn, name, good):
    return [pytest.param(fn, name, tuple(bad if j == i else g for j, g in enumerate(good)), id=f"{name}-arg{i}-{label}")
            for i in range(len(good)) for label, bad in (("nan", NAN), ("inf", INF), ("neginf", -INF))]


NON_FINITE_CASES = (
    _bad_in_each_position(eoq, "eoq", (5, 5, 5))
    + _bad_in_each_position(z_for_service, "z_for_service", (0.9,))
    + _bad_in_each_position(safety_stock, "safety_stock", (1.5, 2, 3, 4, 5))
    + _bad_in_each_position(reorder_point, "reorder_point", (4, 2, 3))
)


@pytest.mark.parametrize("fn, name, args", NON_FINITE_CASES)
def test_the_non_finite_message_names_the_function_and_says_finite(fn, name, args):
    with pytest.raises(ValueError, match=f"^{name}: every input must be a finite number$"):
        fn(*args)
