"""The recommendation looks levels up by exact value; a level that rounds to 0.975 must not shadow it."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import pipeline, render  # noqa: E402


@pytest.fixture(scope="module")
def base():
    return pipeline.run()


@pytest.mark.parametrize("near, label", [(0.97500001, "rounds to 0.975 at 4 places"), (0.97499999, "same, from below")])
def test_a_level_that_rounds_onto_0975_does_not_shadow_the_exact_row(base, near, label):
    res = dict(base)
    template = next(r for r in base["sensitivity"] if r["service_level"] == 0.975)
    exact = dict(template, safety_stock_units=111111.0)
    other = dict(template, service_level=near, safety_stock_units=222222.0)
    res["sensitivity"] = [r for r in base["sensitivity"] if r["service_level"] != 0.975] + [exact, other]
    text = render.render_recommendation(res)
    assert "to 111,111 units" in text, label
    assert "222,222" not in text
