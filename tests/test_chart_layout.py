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


def rects(svg):
    """(x text, width text, class) of every bar, exactly as written in the SVG."""
    return re.findall(r'<rect x="([^"]+)" y="[^"]+" width="([^"]+)" height="[^"]+" class="(cycle|safety)"', svg)


# Slot formula: bar width = min(90, 0.6 * (720 - 70 - 10) / n) = min(90, 384 / n); the gap between bars is
# (640 - bar * n) / (n + 1); bar i starts at 70 + gap * (i + 1) + bar * i.
#   n = 13:  bar = 384/13 = 29.5385 (:g), gap = 256/14 = 18.2857; first x = 70 + 18.2857 = 88.3;
#            last x (i = 12) = 70 + 18.2857 * 13 + 29.5385 * 12 = 662.1758 -> 662.2. (:.0f would say 30.)
#   n = 199: bar = 384/199 = 1.92965 (:g), gap = 256/200 = 1.28; first x = 70 + 1.28 = 71.28 -> 71.3;
#            last x (i = 198) = 70 + 1.28 * 199 + 1.92965 * 198 = 706.79 -> 706.8. (:.0f would say 2.)
@pytest.mark.parametrize("n, width, first_x, last_x", [(13, "29.5385", "88.3", "662.2"), (199, "1.92965", "71.3", "706.8")])
def test_bar_width_and_edge_positions_are_exact_at_many_levels(n, width, first_x, last_x):
    got = rects(chart(n))
    assert len(got) == 2 * n
    assert {w for _, w, _ in got} == {width}
    cycle = [x for x, _, c in got if c == "cycle"]
    assert (cycle[0], cycle[-1]) == (first_x, last_x)
    safety = [x for x, _, c in got if c == "safety"]
    assert (safety[0], safety[-1]) == (first_x, last_x)


@pytest.mark.parametrize("cls", ["cycle", "safety"])
def test_each_bar_kind_writes_its_width_with_four_decimals_at_most(cls):
    """At 13 levels :g gives 29.5385, where :.0f gives 30 and repr gives 29.53846153846154."""
    assert {w for _, w, c in rects(chart(13)) if c == cls} == {"29.5385"}
