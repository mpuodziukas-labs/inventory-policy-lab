"""Plant a wrong formula and prove the simulation check goes RED on it."""
import math
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from policy.formulas import safety_stock


def safety_stock_dropped_scaling(z, lead_time, sigma_d, mean_d, sigma_l):
    """Planted fault: sigma_d is not scaled by lead time."""
    return z * math.sqrt(sigma_d**2 + mean_d**2 * sigma_l**2)


def service_check(results):
    """GREEN when the mean achieved cycle service level is within tolerance of target."""
    s = results["summary"]
    return s["mean_service_level"] >= s["target"] - s["tolerance"]


def run(planted_fn=safety_stock_dropped_scaling):
    from lab import pipeline

    good = service_check(pipeline.run())
    caught = not service_check(pipeline.run(safety_stock_fn=planted_fn))
    print(f"correct formula check green: {good}")
    print(f"planted fault caught (check red): {caught}")
    return 0 if good and caught else 1


if __name__ == "__main__":
    sys.exit(run())
