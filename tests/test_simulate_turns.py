"""Stock turns when no stock is ever held."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from policy.simulate import simulate  # noqa: E402


def test_a_zero_week_lead_that_would_leave_the_shelf_empty_is_rejected():
    # a zero-week lead time never delivers, so turns could only be reported as 0 for an input the guard now refuses
    with pytest.raises(ValueError, match=r"lead values must be whole weeks of at least 1"):
        simulate([5], 0, 1, [0], [1.0], 1, 4, 0)
