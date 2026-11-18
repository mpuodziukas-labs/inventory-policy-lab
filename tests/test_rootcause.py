from lab.rootcause import decompose, dominant_cause


def test_variance_decomposition_hand_worked():
    """L=2, sigma_d=10, d=50, sigma_L=0.5:
    demand part = 2*100 = 200; lead-time part = 50^2*0.5^2 = 625; total 825.
    Shares: 200/825 = 0.2424, 625/825 = 0.7576."""
    sd, sl = decompose(2, 10, 50, 0.5)
    assert abs(sd - 200 / 825) < 1e-12
    assert abs(sl - 625 / 825) < 1e-12
    assert abs(sd + sl - 1.0) < 1e-12
    assert dominant_cause(sd, sl) == "lead-time variability"
    assert dominant_cause(0.7, 0.3) == "demand variability"


def test_decompose_rejects_bad_inputs_with_the_message_a_reader_sees():
    import pytest

    msg = "lead time, standard deviations and mean demand must be finite and non-negative"
    with pytest.raises(ValueError, match="^" + msg + "$"):
        decompose(2, -1, 50, 0.5)


def test_decompose_tiny_demand_total_is_not_treated_as_zero():
    """Total 1e-7 * (1e-3)^2 = 1e-13: far below 1e-12 but not zero, so the shares are (1, 0)."""
    assert decompose(1e-7, 1e-3, 0.0, 0.0) == (1.0, 0.0)


def test_decompose_tiny_lead_time_total_is_not_treated_as_zero():
    """Total (1e-3)^2 * (1e-5)^2 = 1e-16 from the lead-time term only, so the shares are (0, 1)."""
    assert decompose(0.0, 0.0, 1e-3, 1e-5) == (0.0, 1.0)


def test_decompose_subnormal_total_is_not_treated_as_zero():
    """5e-324 is reachable: lead time 5e-324 with sigma_d 1 gives a total of exactly 5e-324."""
    assert 0.0 < 5e-324 * 1.0**2 == 5e-324
    assert decompose(5e-324, 1.0, 0.0, 0.0) == (1.0, 0.0)
