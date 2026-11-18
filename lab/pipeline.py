"""Run the whole analysis from the vendored CSVs and config.json."""
import csv
import json
import math
import re
from pathlib import Path
from statistics import mean, stdev

from lab import forecast as fc
from lab.rootcause import decompose, dominant_cause
from policy.formulas import eoq, reorder_point, safety_stock, z_for_service
from policy.simulate import simulate

ROOT = Path(__file__).resolve().parent.parent
WEEKS_PER_YEAR = 52
# Weeks are compared as text, so every label must have the same width: year, dash, W, two digits 01 to 53.
WEEK_FORMAT = re.compile(r"\d{4}-W(0[1-9]|[1-4]\d|5[0-3])", re.ASCII)


def load_config():
    try:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ValueError("config.json not found") from e
    except UnicodeDecodeError as e:
        raise ValueError("config.json is not valid UTF-8") from e
    except json.JSONDecodeError as e:
        raise ValueError("config.json is not valid JSON") from e
    if not isinstance(cfg, dict):
        raise ValueError("config.json must be a JSON object")
    return cfg


# Every key the code reads, in config.json order, with the type it must have.
CONFIG_KEYS = (
    ("seed", "whole"), ("service_target", "number"), ("service_levels", "numbers"),
    ("lead_time_weeks", "lead"), ("review_period_weeks", "whole"), ("ordering_cost_per_order", "number"),
    ("holding_rate_per_year", "number"), ("ma_window", "whole"), ("ses_alpha", "number"),
    ("min_train_weeks", "whole"), ("sim_weeks", "whole"), ("sim_warmup_weeks", "whole"),
    ("tolerance", "number"),
)


def _is_number(v):
    return type(v) in (int, float)


def _check_config_types(cfg):
    for key, _ in CONFIG_KEYS:
        if key not in cfg:
            raise ValueError(f"config is missing {key}")
    for key, kind in CONFIG_KEYS:
        v = cfg[key]
        if kind == "number" and not _is_number(v):
            raise ValueError(f"{key} must be a number")
        if kind == "whole" and type(v) is not int:
            raise ValueError(f"{key} must be a whole number")
        if kind == "numbers" and not (isinstance(v, list) and all(_is_number(x) for x in v)):
            raise ValueError(f"{key} must be a list of numbers")
        if kind == "lead":
            if not isinstance(v, dict):
                raise ValueError("lead_time_weeks must be an object with values and probs")
            for sub in ("values", "probs"):
                if sub not in v:
                    raise ValueError(f"config is missing lead_time_weeks.{sub}")
            if not (isinstance(v["values"], list) and all(type(x) is int for x in v["values"])):
                raise ValueError("lead_time_weeks.values must be a list of whole numbers")
            if not (isinstance(v["probs"], list) and all(_is_number(x) for x in v["probs"])):
                raise ValueError("lead_time_weeks.probs must be a list of numbers")


def validate_config(cfg):
    _check_config_types(cfg)
    if cfg["service_target"] not in cfg["service_levels"]:
        raise ValueError(f"service_levels must include the service target {cfg['service_target']}")
    if 0.95 not in cfg["service_levels"] or 0.975 not in cfg["service_levels"]:
        raise ValueError("service_levels must include 0.95 and 0.975, the two levels the report compares")
    if not all(0.5 <= v < 1 for v in (cfg["service_target"], *cfg["service_levels"])):
        raise ValueError("service target and service levels must be at least 0.5 and below 1")
    if len(set(cfg["service_levels"])) != len(cfg["service_levels"]):
        raise ValueError("service_levels must not repeat a level")
    if not (math.isfinite(cfg["tolerance"]) and cfg["tolerance"] >= 0):
        raise ValueError("tolerance must be finite and not negative")
    if not 0 < cfg["ses_alpha"] <= 1:
        raise ValueError("ses_alpha must be above 0 and at most 1")
    for key in ("ordering_cost_per_order", "holding_rate_per_year"):
        if not (math.isfinite(cfg[key]) and cfg[key] > 0):
            raise ValueError(f"{key} must be finite and above 0")
    if cfg["review_period_weeks"] < 1:
        raise ValueError("review_period_weeks must be a whole number of at least 1")
    values, probs = cfg["lead_time_weeks"]["values"], cfg["lead_time_weeks"]["probs"]
    if any(v < 1 for v in values):
        raise ValueError("lead_time_weeks.values must be whole weeks of at least 1")
    if len(values) != len(probs):
        raise ValueError("lead_time_weeks.values and probs must have the same length")
    if any(p < 0 for p in probs):
        raise ValueError("lead_time_weeks.probs cannot be negative")
    if not abs(sum(probs) - 1) <= 1e-9:
        raise ValueError("lead_time_weeks.probs must sum to 1")


def _read_rows(name, columns):
    """Rows of a data file as dicts; ValueError names the file when a column is missing."""
    # csv refuses a cell over 131072 characters with its own error; lift that cap for this read so a long
    # cell reaches the units and price checks, then put it back.
    old_limit = csv.field_size_limit(2**31 - 1)
    try:
        with open(ROOT / "data" / name, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for col in columns:
                if col not in (reader.fieldnames or []):
                    raise ValueError(f"{name}: missing column {col}")
            return list(reader)
    except FileNotFoundError as e:
        raise ValueError(f"{name}: file not found") from e
    finally:
        csv.field_size_limit(old_limit)


def load_series():
    rows = _read_rows("weekly_demand.csv", ("iso_week", "stock_code", "units"))
    if not rows:
        raise ValueError("weekly_demand.csv: no data rows")
    series, seen, weeks_of = {}, set(), {}
    for n, r in enumerate(rows, start=2):
        code, week = r["stock_code"], r["iso_week"]
        if code is None or week is None:
            raise ValueError("weekly_demand.csv: a row is missing its stock code or week")
        if code != code.strip():
            raise ValueError(f"weekly_demand.csv: stock code has surrounding whitespace: '{code}'")
        if week != week.strip():
            raise ValueError(f"weekly_demand.csv: week has surrounding whitespace: '{week}'")
        if not WEEK_FORMAT.fullmatch(week):
            raise ValueError(f"weekly_demand.csv: row {n}: iso_week '{week}' is not a week like 2011-W07 (week 01 to 53)")
        if (code, week) in seen:
            raise ValueError(f"weekly_demand.csv: duplicate row for SKU {code} in week {week}")
        seen.add((code, week))
        prev = weeks_of.setdefault(code, [])
        if prev and week < prev[-1]:
            raise ValueError(
                f"weekly_demand.csv: row {n}: weeks for SKU {code} must be in ascending order, "
                f"but {week} follows {prev[-1]}")
        prev.append(week)
        cell = r["units"]
        try:
            units = int(cell) if isinstance(cell, str) and cell.isascii() and cell.isdigit() else -1
        except ValueError:
            units = -1
        if units < 0:
            raise ValueError(
                f"weekly_demand.csv: units for SKU {code} in week {week} must be a whole number of at least 0")
        series.setdefault(code, []).append(units)
    first = sorted(weeks_of)[0]
    for code in sorted(weeks_of):
        if len(weeks_of[code]) == len(weeks_of[first]) and weeks_of[code] != weeks_of[first]:
            raise ValueError(f"weekly_demand.csv: SKU {code} covers different weeks than SKU {first}")
    return {k: series[k] for k in sorted(series)}


def load_prices():
    prices = {}
    for r in _read_rows("sku_price.csv", ("stock_code", "median_unit_price", "description")):
        code, cell = r["stock_code"], r["median_unit_price"]
        if code is None:
            raise ValueError("sku_price.csv: a row is missing its stock code")
        if code != code.strip():
            raise ValueError(f"sku_price.csv: stock code has surrounding whitespace: '{code}'")
        if code in prices:
            raise ValueError(f"sku_price.csv: duplicate row for SKU {code}")
        if isinstance(cell, str) and cell != cell.strip():
            raise ValueError(
                f"sku_price.csv: median_unit_price for SKU {code} has surrounding whitespace: '{cell}'")
        try:
            price = float(cell) if isinstance(cell, str) and cell.isascii() and "_" not in cell else math.nan
        except ValueError:
            price = math.nan
        if not (math.isfinite(price) and price > 0):
            raise ValueError(
                f"sku_price.csv: median_unit_price for SKU {code} must be a finite number above 0")
        if r["description"] is None:
            raise ValueError(f"sku_price.csv: description missing for SKU {code}")
        prices[code] = (price, r["description"])
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
        if len(ys) < 2:  # stdev needs two points; a one-week series has no test window either
            raise ValueError(f"SKU {code} has an empty test window: MAE is undefined: "
                             "no test weeks (the series is no longer than the training minimum)")
        d, sd = mean(ys), stdev(ys)
        h = cfg["holding_rate_per_year"] * price
        try:
            q = max(1, round(eoq(d * WEEKS_PER_YEAR, cfg["ordering_cost_per_order"], h)))
        except ValueError as e:
            raise ValueError(f"SKU {code} has no demand in any week: {e}") from e
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
            try:
                row[f"mae_{name}"] = fc.mae(a_, f_)
            except ValueError as e:
                raise ValueError(f"SKU {code} has an empty test window: {e}") from e
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
