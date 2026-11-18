import math

from policy.formulas import eoq, reorder_point, safety_stock, z_for_service
from lab.selftest import safety_stock_dropped_scaling


def test_eoq_hand_worked_simple():
    """D=1000, S=10, H=2: Q = sqrt(2*1000*10/2) = sqrt(10000) = 100."""
    assert eoq(1000, 10, 2) == 100.0


def test_eoq_hand_worked_textbook():
    """Textbook case D=1500, S=625, H=130:
    Q = sqrt(2*1500*625/130) = sqrt(14423.08) = 120.1 (rounded to 1 dp)."""
    assert round(eoq(1500, 625, 130), 1) == 120.1


def test_eoq_rises_with_demand():
    values = [eoq(d, 50, 2) for d in (100, 400, 1600, 6400)]
    assert values == sorted(values) and len(set(values)) == 4


def test_eoq_rejects_nonpositive_inputs():
    for bad in ((0, 10, 2), (100, 0, 2), (100, 10, 0), (-1, 10, 2)):
        try:
            eoq(*bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_z_for_service_known_values():
    """Standard normal: z(0.95)=1.645, z(0.975)=1.960, z(0.99)=2.326."""
    assert abs(z_for_service(0.95) - 1.6449) < 1e-3
    assert abs(z_for_service(0.975) - 1.9600) < 1e-3
    assert abs(z_for_service(0.99) - 2.3263) < 1e-3


def test_safety_stock_worked_example():
    """Published worked example: z=1.65, lead time 8/7 weeks, sigma_d=10,
    d=50, sigma_L=0.07 weeks.
    variance = 8/7*10^2 + (0.07*50)^2 = 114.2857 + 12.25 = 126.5357
    SS = 1.65 * sqrt(126.5357) = 1.65 * 11.2488 = 18.56 (about 19 rolls).
    Demand variability only: 1.65 * sqrt(8/7) * 10 = 17.64 (about 18)."""
    got = safety_stock(1.65, 8 / 7, 10, 50, 0.07)
    assert abs(got - 18.56) < 0.01
    assert round(got) == 19
    only_demand = safety_stock(1.65, 8 / 7, 10, 50, 0.0)
    assert abs(only_demand - 17.64) < 0.01
    assert round(only_demand) == 18


def test_safety_stock_rises_with_service_level():
    values = [
        safety_stock(z_for_service(p), 2, 10, 50, 0.5)
        for p in (0.90, 0.95, 0.975, 0.99)
    ]
    assert values == sorted(values) and len(set(values)) == 4


def test_safety_stock_zero_lead_time_variability_reduces():
    """sigma_L=0: z=1.65, L=4, sigma_d=10 -> 1.65*10*sqrt(4) = 33.0."""
    assert math.isclose(safety_stock(1.65, 4, 10, 50, 0.0), 33.0, rel_tol=1e-12)


def test_safety_stock_hand_worked_decomposition():
    """z=2, L=2, sigma_d=10, d=50, sigma_L=0.5:
    variance = 2*100 + 2500*0.25 = 200 + 625 = 825; SS = 2*sqrt(825) = 57.446."""
    assert abs(safety_stock(2, 2, 10, 50, 0.5) - 57.446) < 1e-3


def test_reorder_point_hand_worked():
    """d=50 per week, L=2 weeks, SS=18.56: ROP = 50*2 + 18.56 = 118.56."""
    assert abs(reorder_point(50, 2, 18.56) - 118.56) < 1e-9


def test_mutant_dropped_lead_time_scaling_changes_result():
    """The planted variant drops the L factor on the demand term. With L=2 the
    result must differ from the correct value (200 vs 100 in the variance)."""
    good = safety_stock(1.65, 2, 10, 50, 0.5)
    bad = safety_stock_dropped_scaling(1.65, 2, 10, 50, 0.5)
    assert bad < good
    assert abs(good - 1.65 * math.sqrt(825)) < 1e-9
    assert abs(bad - 1.65 * math.sqrt(100 + 625)) < 1e-9
