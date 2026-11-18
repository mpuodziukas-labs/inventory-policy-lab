"""Pure inventory formulas. Time unit is the demand period (weeks here)."""
import math
from statistics import NormalDist


def eoq(annual_demand, order_cost, holding_cost):
    """Q* = sqrt(2 D S / H)."""
    if annual_demand <= 0 or order_cost <= 0 or holding_cost <= 0:
        raise ValueError("demand, order cost and holding cost must be positive")
    return math.sqrt(2 * annual_demand * order_cost / holding_cost)


def z_for_service(level):
    """Safety factor for a cycle service level in (0, 1)."""
    return NormalDist().inv_cdf(level)


def safety_stock(z, lead_time, sigma_d, mean_d, sigma_l):
    """z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2); demand and lead time independent."""
    return z * math.sqrt(lead_time * sigma_d**2 + mean_d**2 * sigma_l**2)


def reorder_point(mean_d, lead_time, safety):
    """Expected lead-time demand plus safety stock."""
    return mean_d * lead_time + safety
