"""Config check order (missing keys, then types, both in file order) and the exact edge of every bound."""
import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402

# the order SPEC.md states: config.json file order
FILE_ORDER = ["seed", "service_target", "service_levels", "lead_time_weeks", "review_period_weeks",
              "ordering_cost_per_order", "holding_rate_per_year", "ma_window", "ses_alpha",
              "min_train_weeks", "sim_weeks", "sim_warmup_weeks", "tolerance"]
PAIRS = list(zip(FILE_ORDER, FILE_ORDER[1:]))
KIND = {"seed": "whole", "review_period_weeks": "whole", "ma_window": "whole", "min_train_weeks": "whole",
        "sim_weeks": "whole", "sim_warmup_weeks": "whole", "service_levels": "numbers",
        "lead_time_weeks": "lead"}
BAD_VALUE = {"whole": True, "number": "x", "numbers": "x", "lead": "x"}
TYPE_MSG = {"whole": "{k} must be a whole number", "number": "{k} must be a number",
            "numbers": "{k} must be a list of numbers",
            "lead": "lead_time_weeks must be an object with values and probs"}


def cfg(**over):
    d = copy.deepcopy(pipeline.load_config())
    d.update(over)
    return d


def bad(msg, **over):
    with pytest.raises(ValueError, match="^" + re.escape(msg) + "$"):
        pipeline.validate_config(cfg(**over))


def ok(**over):
    pipeline.validate_config(cfg(**over))


def lead(values, probs):
    return {"values": values, "probs": probs}


def test_file_order_in_this_test_is_the_committed_config_order():
    assert FILE_ORDER == list(pipeline.load_config())


@pytest.mark.parametrize("first,second", PAIRS)
def test_when_two_keys_are_missing_the_earlier_one_in_file_order_is_named(first, second):
    c = cfg()
    del c[first], c[second]
    with pytest.raises(ValueError, match="^" + re.escape(f"config is missing {first}") + "$"):
        pipeline.validate_config(c)


def test_every_missing_key_is_reported_before_any_type_error():
    c = cfg(seed=True)
    del c["tolerance"]
    with pytest.raises(ValueError, match="^config is missing tolerance$"):
        pipeline.validate_config(c)


@pytest.mark.parametrize("first,second", PAIRS)
def test_when_two_keys_have_a_wrong_type_the_earlier_one_in_file_order_is_named(first, second):
    kinds = [KIND.get(k, "number") for k in (first, second)]
    c = cfg()
    c[first], c[second] = BAD_VALUE[kinds[0]], BAD_VALUE[kinds[1]]
    with pytest.raises(ValueError, match="^" + re.escape(TYPE_MSG[kinds[0]].format(k=first)) + "$"):
        pipeline.validate_config(c)


def test_lead_values_type_is_reported_before_lead_probs_type():
    bad("lead_time_weeks.values must be a list of whole numbers", lead_time_weeks=lead(["1"], ["x"]))


# ---- service target and levels

def test_service_target_must_equal_a_level_exactly_not_nearly():
    bad("service_levels must include the service target 0.951", service_target=0.951)
    bad("service_levels must include the service target 0.9500001", service_target=0.9500001)
    bad("service_levels must include the service target 0.95", service_levels=[0.9, 0.9500001, 0.975, 0.99])


def test_levels_0_95_and_0_975_must_be_listed_exactly_not_nearly():
    msg = "service_levels must include 0.95 and 0.975, the two levels the report compares"
    bad(msg, service_target=0.9501, service_levels=[0.9, 0.9501, 0.975, 0.99])
    bad(msg, service_target=0.9500001, service_levels=[0.9, 0.9500001, 0.975, 0.99])
    bad(msg, service_levels=[0.9, 0.95, 0.9750001, 0.99])


def test_range_lower_bound_is_exactly_one_half_and_the_upper_bound_is_exclusive():
    msg = "service target and service levels must be at least 0.5 and below 1"
    bad(msg, service_target=0.49995, service_levels=[0.49995, 0.95, 0.975])
    bad(msg, service_levels=[0.49995, 0.95, 0.975])
    bad(msg, service_levels=[0.95, 0.975, 1])
    ok(service_target=0.5, service_levels=[0.5, 0.95, 0.975])
    ok(service_levels=[0.95, 0.975, 0.9999999])


# ---- tolerance and smoothing

def test_tolerance_lower_edge_is_exactly_zero():
    for t in (-1e-10, -1e-9, -1e-12, -1e-300):
        bad("tolerance must be finite and not negative", tolerance=t)
    ok(tolerance=0)
    ok(tolerance=0.0)


def test_tolerance_has_no_upper_cap():
    ok(tolerance=1.0)
    ok(tolerance=5)


def test_ses_alpha_upper_edge_is_exactly_one_and_the_lower_edge_is_open():
    msg = "ses_alpha must be above 0 and at most 1"
    bad(msg, ses_alpha=1.00000000005)
    bad(msg, ses_alpha=1.0000000001)
    bad(msg, ses_alpha=0)
    ok(ses_alpha=1)
    ok(ses_alpha=1.0)
    ok(ses_alpha=1e-300)


# ---- lead-time distribution

def test_lead_values_and_probs_must_have_equal_length_in_both_directions():
    msg = "lead_time_weeks.values and probs must have the same length"
    bad(msg, lead_time_weeks=lead([1, 2, 3, 4], [0.125, 0.75, 0.125]))
    bad(msg, lead_time_weeks=lead([1, 2, 3], [0.5, 0.5]))
    bad(msg, lead_time_weeks=lead([1, 2], [0.125, 0.75, 0.125]))


def test_a_zero_probability_is_allowed():
    ok(lead_time_weeks=lead([1, 2, 3], [0.0, 0.75, 0.25]))
    ok(lead_time_weeks=lead([1, 2, 3], [0, 0.75, 0.25]))


def test_a_probability_below_zero_is_rejected_however_small():
    msg = "lead_time_weeks.probs cannot be negative"
    bad(msg, lead_time_weeks=lead([1, 2, 3], [-1e-13, 0.875, 0.1250000000001]))
    bad(msg, lead_time_weeks=lead([1, 2, 3], [-1e-300, 0.75, 0.25]))


def test_probability_sum_tolerance_is_1e_9_on_both_sides_of_one():
    msg = "lead_time_weeks.probs must sum to 1"
    bad(msg, lead_time_weeks=lead([1, 2, 3], [0.125, 0.75, 0.12500001]))
    bad(msg, lead_time_weeks=lead([1, 2, 3], [0.125, 0.75, 0.12499999]))
    bad(msg, lead_time_weeks=lead([1, 2, 3], [0.125, 0.75, 0.125000002]))
    ok(lead_time_weeks=lead([1, 2, 3], [0.125, 0.75, 0.1250000005]))
    ok(lead_time_weeks=lead([1, 2, 3], [0.125, 0.75, 0.1249999995]))
