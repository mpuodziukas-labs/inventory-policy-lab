"""Order of the simulate input checks: one input breaks two checks at once, the earlier check is reported."""
import pytest

from policy.simulate import simulate


def test_a_fractional_negative_warm_up_is_reported_as_not_whole_before_negative():
    with pytest.raises(ValueError, match=r"^warmup must be a whole number$"):
        simulate([5, 6, 7], 10, 5, [1, 2], [0.5, 0.5], 1, 20, -1.5)


def test_a_length_mismatch_is_reported_before_a_negative_probability():
    with pytest.raises(ValueError, match=r"^lead values and probabilities must have the same length$"):
        simulate([5, 6, 7], 10, 5, [1, 2], [-0.5, 1.0, 0.5], 1, 20, 2)


def test_a_negative_probability_is_reported_before_a_probability_sum_that_is_not_one():
    with pytest.raises(ValueError, match=r"^lead probabilities cannot be negative$"):
        simulate([5, 6, 7], 10, 5, [1, 2], [-0.5, 0.25], 1, 20, 2)
