"""Stock turns when no stock is ever held."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from policy.simulate import simulate  # noqa: E402


def test_turns_is_zero_when_average_inventory_is_zero():
    # a zero-week lead time never delivers, so the shelf is empty in every counted week
    out = simulate([5], 0, 1, [0], [1.0], 1, 4, 0)
    assert out["avg_inventory"] == 0.0
    assert out["turns"] == 0.0
