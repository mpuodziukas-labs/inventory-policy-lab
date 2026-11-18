"""Run the whole analysis from the vendored CSVs and config.json."""
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev

from lab import forecast as fc
from lab.rootcause import decompose, dominant_cause
from policy.formulas import eoq, reorder_point, safety_stock, z_for_service
from policy.simulate import simulate

ROOT = Path(__file__).resolve().parent.parent
WEEKS_PER_YEAR = 52


def load_config():
    return json.loads((ROOT / "config.json").read_text())


def load_series():
    series, order = {}, []
    with open(ROOT / "data" / "weekly_demand.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["stock_code"] not in series:
                series[r["stock_code"]] = []
                order.append(r["stock_code"])
            series[r["stock_code"]].append(int(r["units"]))
    return {k: series[k] for k in sorted(order)}


def load_prices():
    with open(ROOT / "data" / "sku_price.csv", newline="") as f:
        return {r["stock_code"]: (float(r["median_unit_price"]), r["description"]) for r in csv.DictReader(f)}


def skewness(xs):
    m, s = mean(xs), stdev(xs)
    if s == 0:
        return 0.0  # constant series: skewness is undefined, 0 by convention
    return sum(((x - m) / s) ** 3 for x in xs) / len(xs)


def run(safety_stock_fn=safety_stock):
    cfg = load_config()
    series, prices = load_series(), load_prices()
    lv, lp = cfg["lead_time_weeks"]["values"], cfg["lead_time_weeks"]["probs"]
    lead_mean = sum(v * p for v, p in zip(lv, lp))
    lead_sd = math.sqrt(sum(p * (v - lead_mean) ** 2 for v, p in zip(lv, lp)))
    protect = lead_mean + cfg["review_period_weeks"]
    target, tol = cfg["service_target"], cfg["tolerance"]
    z = z_for_service(target)
    methods = {
        "naive": fc.naive_forecast,
        "ma": lambda h: fc.moving_average(h, cfg["ma_window"]),
        "ses": lambda h: fc.ses(h, cfg["ses_alpha"]),
    }
    err_sum = {m: 0.0 for m in methods}
    act_sum = 0.0
    skus = []
    for i, (code, ys) in enumerate(series.items()):
        price, desc = prices[code]
        d, sd = mean(ys), stdev(ys)
        h = cfg["holding_rate_per_year"] * price
        q = max(1, round(eoq(d * WEEKS_PER_YEAR, cfg["ordering_cost_per_order"], h)))
        ss = safety_stock_fn(z, protect, sd, d, lead_sd)
        rop = reorder_point(d, protect, ss)
        sim = simulate(ys, rop, q, lv, lp, cfg["seed"] + i, cfg["sim_weeks"], cfg["sim_warmup_weeks"])
        share_d, share_l = decompose(protect, sd, d, lead_sd)
        row = {
            "code": code, "description": desc, "price": price,
            "mean_weekly": d, "sd_weekly": sd, "skew": skewness(ys),
            "eoq": q, "safety_stock": ss, "reorder_point": rop,
            "share_demand": share_d, "share_lead": share_l,
            "cause": dominant_cause(share_d, share_l),
            **sim,
        }
        row["meets_target"] = sim["cycle_service_level"] >= target - tol
        for name, fn in methods.items():
            f_, a_ = fc.rolling_origin(ys, fn, cfg["min_train_weeks"])
            row[f"mae_{name}"] = fc.mae(a_, f_)
            try:
                row[f"wape_{name}"] = fc.wape(a_, f_)
            except ValueError as e:
                raise ValueError(f"SKU {code} has no demand in its test window: {e}") from e
            row[f"next_{name}"] = fn(ys)
            err_sum[name] += sum(abs(x - y) for x, y in zip(a_, f_))
        act_sum += sum(a_)
        skus.append(row)
    sensitivity = []
    for level in cfg["service_levels"]:
        zl = z_for_service(level)
        ss_units = ss_cost = cycle_cost = 0.0
        for row in skus:
            ss_l = safety_stock_fn(zl, protect, row["sd_weekly"], row["mean_weekly"], lead_sd)
            hold = cfg["holding_rate_per_year"] * row["price"]
            ss_units += ss_l
            ss_cost += hold * ss_l
            cycle_cost += hold * row["eoq"] / 2
        sensitivity.append({
            "service_level": level, "z": zl, "safety_stock_units": ss_units,
            "safety_stock_holding_cost": ss_cost,
            "total_holding_cost": ss_cost + cycle_cost,
        })
    summary = {
        "sku_count": len(skus),
        "meeting_target": sum(1 for r in skus if r["meets_target"]),
        "target": target, "tolerance": tol, "weeks": len(next(iter(series.values()))),
        "mean_service_level": mean(r["cycle_service_level"] for r in skus),
        "mean_fill_rate": mean(r["fill_rate"] for r in skus),
        "lead_mean": lead_mean, "lead_sd": lead_sd, "protect": protect,
        "wape": {m: err_sum[m] / act_sum for m in methods},
        "ses_beats_naive": sum(1 for r in skus if r["wape_ses"] < r["wape_naive"]),
    }
    return {"config": cfg, "skus": skus, "sensitivity": sensitivity, "summary": summary}
