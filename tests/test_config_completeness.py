"""validate_config checks every key the code reads, by presence, then type, then range, in a fixed order."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402

KEYS = ["seed", "service_target", "service_levels", "lead_time_weeks", "review_period_weeks",
        "ordering_cost_per_order", "holding_rate_per_year", "ma_window", "ses_alpha", "min_train_weeks",
        "sim_weeks", "sim_warmup_weeks", "tolerance"]
NAN, INF = float("nan"), float("inf")


def exact(text):
    return "^" + re.escape(text) + "$"


def cfg(**overrides):
    return dict(pipeline.load_config(), **overrides)


def test_the_key_list_in_this_file_is_every_key_of_the_committed_config():
    assert sorted(KEYS) == sorted(pipeline.load_config())


@pytest.mark.parametrize("key", KEYS)
def test_a_missing_key_is_a_value_error_naming_the_key(key):
    c = cfg()
    c.pop(key)
    with pytest.raises(ValueError, match=exact(f"config is missing {key}")):
        pipeline.validate_config(c)


@pytest.mark.parametrize("sub", ["values", "probs"])
def test_a_missing_lead_time_part_is_named(sub):
    lt = dict(pipeline.load_config()["lead_time_weeks"])
    lt.pop(sub)
    with pytest.raises(ValueError, match=exact(f"config is missing lead_time_weeks.{sub}")):
        pipeline.validate_config(cfg(lead_time_weeks=lt))


WHOLE = ["seed", "review_period_weeks", "ma_window", "min_train_weeks", "sim_weeks", "sim_warmup_weeks"]
NUMBER = ["service_target", "tolerance", "ses_alpha", "ordering_cost_per_order", "holding_rate_per_year"]


@pytest.mark.parametrize("key", WHOLE)
@pytest.mark.parametrize("value", ["7", None, [7], 7.0, 7.5, True, {"a": 1}])
def test_a_whole_number_key_with_any_other_type_is_a_value_error(key, value):
    with pytest.raises(ValueError, match=exact(f"{key} must be a whole number")):
        pipeline.validate_config(cfg(**{key: value}))


@pytest.mark.parametrize("key", NUMBER)
@pytest.mark.parametrize("value", ["0.5", None, [0.5], True, {"a": 1}])
def test_a_number_key_with_any_other_type_is_a_value_error(key, value):
    with pytest.raises(ValueError, match=exact(f"{key} must be a number")):
        pipeline.validate_config(cfg(**{key: value}))


@pytest.mark.parametrize("value", [0.95, "0.95", None, [0.95, "0.975"], [True], {"a": 1}])
def test_service_levels_must_be_a_list_of_numbers(value):
    with pytest.raises(ValueError, match=exact("service_levels must be a list of numbers")):
        pipeline.validate_config(cfg(service_levels=value))


@pytest.mark.parametrize("value", [None, [1], "x", 3])
def test_lead_time_weeks_must_be_an_object(value):
    with pytest.raises(ValueError, match=exact("lead_time_weeks must be an object with values and probs")):
        pipeline.validate_config(cfg(lead_time_weeks=value))


@pytest.mark.parametrize("values", [[1.0, 2], 1, "12", None, [True]])
def test_lead_time_values_must_be_a_list_of_whole_numbers(values):
    lt = {"values": values, "probs": [0.5, 0.5]}
    with pytest.raises(ValueError, match=exact("lead_time_weeks.values must be a list of whole numbers")):
        pipeline.validate_config(cfg(lead_time_weeks=lt))


@pytest.mark.parametrize("probs", [0.5, "ab", None, [0.5, "0.5"], [True, 0.5]])
def test_lead_time_probs_must_be_a_list_of_numbers(probs):
    lt = {"values": [1, 2], "probs": probs}
    with pytest.raises(ValueError, match=exact("lead_time_weeks.probs must be a list of numbers")):
        pipeline.validate_config(cfg(lead_time_weeks=lt))


LEAD = {"values": [1, 2, 3], "probs": [0.125, 0.75, 0.125]}
RANGE_CASES = [
    ({"review_period_weeks": 0}, "review_period_weeks must be a whole number of at least 1"),
    ({"review_period_weeks": -1}, "review_period_weeks must be a whole number of at least 1"),
    ({"ordering_cost_per_order": 0}, "ordering_cost_per_order must be finite and above 0"),
    ({"ordering_cost_per_order": -5.0}, "ordering_cost_per_order must be finite and above 0"),
    ({"ordering_cost_per_order": NAN}, "ordering_cost_per_order must be finite and above 0"),
    ({"ordering_cost_per_order": INF}, "ordering_cost_per_order must be finite and above 0"),
    ({"holding_rate_per_year": 0}, "holding_rate_per_year must be finite and above 0"),
    ({"holding_rate_per_year": -0.25}, "holding_rate_per_year must be finite and above 0"),
    ({"holding_rate_per_year": NAN}, "holding_rate_per_year must be finite and above 0"),
    ({"holding_rate_per_year": INF}, "holding_rate_per_year must be finite and above 0"),
    ({"tolerance": INF}, "tolerance must be finite and not negative"),
    ({"tolerance": -INF}, "tolerance must be finite and not negative"),
    ({"service_levels": [0.9, 0.95, 0.95, 0.975]}, "service_levels must not repeat a level"),
    ({"service_levels": [0.9, 0.975, 0.99], "service_target": 0.975},
     "service_levels must include 0.95 and 0.975, the two levels the report compares"),
    ({"service_levels": [0.95, 0.975, NAN]}, "service target and service levels must be at least 0.5 and below 1"),
    ({"lead_time_weeks": {"values": [0, 2, 3], "probs": LEAD["probs"]}},
     "lead_time_weeks.values must be whole weeks of at least 1"),
    ({"lead_time_weeks": {"values": [1, 2], "probs": LEAD["probs"]}},
     "lead_time_weeks.values and probs must have the same length"),
    ({"lead_time_weeks": {"values": [1, 2, 3], "probs": [-0.5, 1.0, 0.5]}},
     "lead_time_weeks.probs cannot be negative"),
    ({"lead_time_weeks": {"values": [1, 2, 3], "probs": [0.1, 0.1, 0.1]}},
     "lead_time_weeks.probs must sum to 1"),
    ({"lead_time_weeks": {"values": [1, 2, 3], "probs": [NAN, 0.5, 0.5]}},
     "lead_time_weeks.probs must sum to 1"),
    ({"lead_time_weeks": {"values": [], "probs": []}}, "lead_time_weeks.probs must sum to 1"),
]


@pytest.mark.parametrize("overrides, message", RANGE_CASES)
def test_out_of_range_config_values_are_rejected_up_front(overrides, message):
    with pytest.raises(ValueError, match=exact(message)):
        pipeline.validate_config(cfg(**overrides))


@pytest.mark.parametrize("overrides", [
    {"review_period_weeks": 1}, {"review_period_weeks": 4}, {"seed": -5}, {"seed": 0},
    {"lead_time_weeks": {"values": [1], "probs": [1.0]}},
    {"lead_time_weeks": {"values": [2, 1], "probs": [0.5, 0.5]}},
    {"ordering_cost_per_order": 1}, {"holding_rate_per_year": 1e-9},
    {"service_target": 0.975}, {"service_levels": [0.95, 0.975]},
])
def test_valid_edge_values_are_still_accepted(overrides):
    pipeline.validate_config(cfg(**overrides))


# One input per row breaks two checks at once; the first check in the order below must win.
# Order: missing keys, types in file key order, then target in levels, 0.95 and 0.975 listed,
# range, duplicate levels, tolerance, ses_alpha, ordering cost, holding rate, review period,
# lead values, lead length, lead negative probability, lead probability sum.
BAD_LEAD_VALUES = {"values": [0, 2, 3], "probs": LEAD["probs"]}
ORDER_CASES = [
    ({"seed": "x", "tolerance": "x"}, "seed must be a whole number"),
    ({"tolerance": "x", "service_levels": [0.9, 0.99]}, "tolerance must be a number"),
    ({"service_levels": [0.9, 0.99]},
     "service_levels must include the service target 0.95"),
    ({"service_levels": [0.95, 0.99, 0.3]},
     "service_levels must include 0.95 and 0.975, the two levels the report compares"),
    ({"service_levels": [0.95, 0.975, 0.975, 1.0]},
     "service target and service levels must be at least 0.5 and below 1"),
    ({"service_levels": [0.95, 0.975, 0.975], "tolerance": -1}, "service_levels must not repeat a level"),
    ({"tolerance": -1, "ses_alpha": 0}, "tolerance must be finite and not negative"),
    ({"ses_alpha": 0, "ordering_cost_per_order": 0}, "ses_alpha must be above 0 and at most 1"),
    ({"ordering_cost_per_order": 0, "holding_rate_per_year": 0},
     "ordering_cost_per_order must be finite and above 0"),
    ({"holding_rate_per_year": 0, "review_period_weeks": 0},
     "holding_rate_per_year must be finite and above 0"),
    ({"review_period_weeks": 0, "lead_time_weeks": BAD_LEAD_VALUES},
     "review_period_weeks must be a whole number of at least 1"),
    ({"lead_time_weeks": {"values": [0, 2], "probs": [0.5, 0.25, 0.25]}},
     "lead_time_weeks.values must be whole weeks of at least 1"),
    ({"lead_time_weeks": {"values": [1, 2], "probs": [-0.5, 1.0, 0.5]}},
     "lead_time_weeks.values and probs must have the same length"),
    ({"lead_time_weeks": {"values": [1, 2, 3], "probs": [-0.5, 0.25, 0.25]}},
     "lead_time_weeks.probs cannot be negative"),
]


@pytest.mark.parametrize("overrides, winner", ORDER_CASES)
def test_when_two_checks_fail_at_once_the_earlier_one_in_the_order_is_reported(overrides, winner):
    with pytest.raises(ValueError, match=exact(winner)):
        pipeline.validate_config(cfg(**overrides))


def test_a_missing_key_is_reported_before_a_wrong_type_on_an_earlier_key():
    c = cfg(seed="x")
    c.pop("tolerance")
    with pytest.raises(ValueError, match=exact("config is missing tolerance")):
        pipeline.validate_config(c)


def test_a_bad_config_fails_before_any_data_file_is_read(monkeypatch):
    def boom():
        raise RuntimeError("data was read")

    bad = cfg(tolerance=-1)
    monkeypatch.setattr(pipeline, "load_config", lambda: bad)
    monkeypatch.setattr(pipeline, "load_series", boom)
    monkeypatch.setattr(pipeline, "load_prices", boom)
    with pytest.raises(ValueError, match=exact("tolerance must be finite and not negative")):
        pipeline.run()
