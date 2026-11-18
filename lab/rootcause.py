"""Split lead-time-demand variance into its demand and lead-time parts."""


def decompose(lead_time, sigma_d, mean_d, sigma_l):
    demand_part = lead_time * sigma_d**2
    lead_part = mean_d**2 * sigma_l**2
    total = demand_part + lead_part
    return demand_part / total, lead_part / total


def dominant_cause(share_demand, share_lead):
    return "demand variability" if share_demand >= share_lead else "lead-time variability"
