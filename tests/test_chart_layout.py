"""The cost chart keeps every bar inside the canvas and clear of its neighbours at any level count."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import render  # noqa: E402

CANVAS_W = 720


def chart(n):
    rows = [{"service_level": 0.5 + 0.49 * i / max(n - 1, 1), "z": 0.0, "safety_stock_units": 1.0,
             "safety_stock_holding_cost": 10.0, "total_holding_cost": 100.0 + i} for i in range(n)]
    return render._cost_chart({"sensitivity": rows})


def bars(svg):
    return [(float(x), float(w)) for x, w in re.findall(r'<rect x="([-\d.]+)"[^>]*width="([\d.]+)"[^>]*class="cycle"', svg)]


@pytest.mark.parametrize("n", [1, 2, 4, 8, 20, 50])
def test_every_bar_is_inside_the_canvas_and_clear_of_its_neighbours(n):
    got = bars(chart(n))
    assert len(got) == n
    for x, w in got:
        assert x >= 0
        assert x + w <= CANVAS_W
        assert w > 0
    for (x1, w1), (x2, _) in zip(got, got[1:]):
        assert x1 + w1 <= x2


def test_bars_never_exceed_90_wide():
    assert all(w <= 90 for _, w in bars(chart(1)))


def test_four_levels_keep_the_published_90_wide_bars():
    assert {w for _, w in bars(chart(4))} == {90.0}
