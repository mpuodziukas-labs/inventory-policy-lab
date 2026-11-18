"""The reorder loop ends because each order raises on-order stock by the order quantity."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from policy import simulate as sim  # noqa: E402


def test_orders_placed_are_bounded_and_exact_for_a_hand_traced_run(monkeypatch):
    """Demand 3 a week, reorder point 10, order 5, lead 1 week: orders go out in weeks 2, 4 and 5."""
    draws = []

    def counting_draw(rng, values, probs):
        draws.append(1)
        if len(draws) > 50:
            raise AssertionError("order loop is not terminating: on_order is not growing by the order quantity")
        return values[-1]

    monkeypatch.setattr(sim, "_draw", counting_draw)
    out = sim.simulate([3], 10, 5, [1], [1.0], 1, 6, 0)
    assert len(draws) == 3
    assert out["orders"] == 3
