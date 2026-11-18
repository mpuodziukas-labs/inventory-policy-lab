"""Split lead-time-demand variance into its demand and lead-time parts."""
import math


def decompose(lead_time, sigma_d, mean_d, sigma_l):
    if not all(math.isfinite(v) and v >= 0 for v in (lead_time, sigma_d, mean_d, sigma_l)):
        raise ValueError("lead time, standard deviations and mean demand must be finite and non-negative")
    demand_part = lead_time * sigma_d**2
    lead_part = mean_d**2 * sigma_l**2
    total = demand_part + lead_part
    if total == 0:
        raise ValueError("variance shares are undefined: demand and lead-time variance are both zero")
    return demand_part / total, lead_part / total


def dominant_cause(share_demand, share_lead):
    return "demand variability" if share_demand >= share_lead else "lead-time variability"
