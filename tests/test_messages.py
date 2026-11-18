"""Error messages are matched by their key words, so a reworded message is a visible change."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from policy.formulas import eoq  # noqa: E402
from policy.simulate import simulate  # noqa: E402


def test_simulate_rejects_non_positive_weeks_saying_weeks_must_be_positive():
    with pytest.raises(ValueError, match=r"weeks must be positive"):
        simulate([1], 0, 1, [1], [1.0], 1, 0, 0)


def test_simulate_without_completed_cycles_tells_the_user_to_lengthen():
    with pytest.raises(ValueError, match=r"no completed order cycles; lengthen the simulation"):
        simulate([0], 0, 1, [1], [1.0], 1, 3, 0)


@pytest.mark.parametrize("args", [(0, 50, 1), (100, 0, 1), (100, 50, 0)])
def test_eoq_error_names_all_three_inputs_and_positive(args):
    with pytest.raises(ValueError, match=r"demand, order cost and holding cost must be positive"):
        eoq(*args)


def test_wape_zero_sum_message_says_the_actuals_sum_to_zero():
    with pytest.raises(ValueError, match=r"WAPE is undefined: the actuals sum to zero"):
        fc.wape([0, 0], [1, 1])
