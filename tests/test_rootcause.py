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
