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


def validate_config(cfg):
    if cfg["service_target"] not in cfg["service_levels"]:
        raise ValueError(f"service_levels must include the service target {cfg['service_target']}")
    if not (math.isfinite(cfg["tolerance"]) and cfg["tolerance"] >= 0):
        raise ValueError("tolerance must be finite and not negative")
    if not 0 < cfg["ses_alpha"] <= 1:
        raise ValueError("ses_alpha must be above 0 and at most 1")
    for key in ("sim_weeks", "sim_warmup_weeks"):
        if type(cfg[key]) is not int:
            raise ValueError(f"{key} must be a whole number")


def _read_rows(name, columns):
    """Rows of a data file as dicts; ValueError names the file when a column is missing."""
    with open(ROOT / "data" / name, newline="") as f:
        reader = csv.DictReader(f)
        for col in columns:
            if col not in (reader.fieldnames or []):
                raise ValueError(f"{name}: missing column {col}")
        return list(reader)


def load_series():
    rows = _read_rows("weekly_demand.csv", ("iso_week", "stock_code", "units"))
    if not rows:
        raise ValueError("weekly_demand.csv: no data rows")
    series, seen = {}, set()
    for r in rows:
        code, week = r["stock_code"], r["iso_week"]
        if (code, week) in seen:
            raise ValueError(f"weekly_demand.csv: duplicate row for SKU {code} in week {week}")
        seen.add((code, week))
        try:
            units = int(r["units"])
        except (TypeError, ValueError):
            units = -1
        if units < 0:
            raise ValueError(
                f"weekly_demand.csv: units for SKU {code} in week {week} must be a whole number of at least 0")
        series.setdefault(code, []).append(units)
    return {k: series[k] for k in sorted(series)}


def load_prices():
    prices = {}
    for r in _read_rows("sku_price.csv", ("stock_code", "median_unit_price", "description")):
        try:
            price = float(r["median_unit_price"])
        except (TypeError, ValueError):
            price = math.nan
        if not (math.isfinite(price) and price > 0):
            raise ValueError(
                f"sku_price.csv: median_unit_price for SKU {r['stock_code']} must be a finite number above 0")
        prices[r["stock_code"]] = (price, r["description"])
    return prices


def skewness(xs):
    m, s = mean(xs), stdev(xs)
    if s == 0:
        return 0.0  # constant series: skewness is undefined, 0 by convention
    return sum(((x - m) / s) ** 3 for x in xs) / len(xs)


def run(safety_stock_fn=safety_stock):
    cfg = load_config()
    validate_config(cfg)
    series, prices = load_series(), load_prices()
    first_code = next(iter(series))
    weeks = len(series[first_code])
    for code, ys in series.items():
        if len(ys) != weeks:
            raise ValueError(
                f"SKU {code} has {len(ys)} weeks but SKU {first_code} has {weeks}; every SKU needs the same number of weeks")
    for code in series:
        if code not in prices:
            raise ValueError(f"sku_price.csv: no price row for SKU {code}")
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
        "target": target, "tolerance": tol, "weeks": weeks,
        "mean_service_level": mean(r["cycle_service_level"] for r in skus),
        "mean_fill_rate": mean(r["fill_rate"] for r in skus),
        "lead_mean": lead_mean, "lead_sd": lead_sd, "protect": protect,
        "wape": {m: err_sum[m] / act_sum for m in methods},
        "ses_beats_naive": sum(1 for r in skus if r["wape_ses"] < r["wape_naive"]),
    }
    return {"config": cfg, "skus": skus, "sensitivity": sensitivity, "summary": summary}
