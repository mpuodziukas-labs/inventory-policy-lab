#!/usr/bin/env python3
"""Build data/weekly_demand.csv and data/sku_price.csv from the UCI Online Retail xlsx.

Usage: python3 scripts/make_extract.py "path/to/Online Retail.xlsx" [out_dir]

One-time step: needs openpyxl. Everything else in the repo runs on the vendored CSVs.
"""
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

TOP_SKUS = 40
PRODUCT_CODE = re.compile(r"\d{5}[A-Za-z]{0,2}")


def is_product_code(code):
    """Product codes are five digits plus up to two letters; POST, DOT, M,
    BANK CHARGES and similar service codes do not match."""
    return bool(PRODUCT_CODE.fullmatch(str(code).strip()))


def week_label(dt):
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def aggregate(rows):
    """rows: (invoice, stock_code, quantity, datetime, unit_price).

    Sales (positive quantity) and cancellations (negative quantity on an
    invoice starting with C) are netted per SKU and ISO week. Zero or negative
    prices, other negative rows and non-product codes are dropped. Weekly
    demand is floored at zero.
    """
    net = defaultdict(int)
    for invoice, code, qty, dt, price in rows:
        if not is_product_code(code) or price is None or price <= 0:
            continue
        invoice = str(invoice)
        if qty > 0 and not invoice.startswith("C"):
            pass
        elif qty < 0 and invoice.startswith("C"):
            pass
        else:
            continue
        net[(week_label(dt), str(code).strip())] += int(qty)
    return {k: max(0, v) for k, v in net.items() if k[1]}


def full_weeks(first, last):
    """ISO weeks fully covered by data running from first to last datetime."""
    monday = (first - timedelta(days=first.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if first > monday:
        monday += timedelta(days=7)
    weeks = []
    while monday + timedelta(days=7) <= last + timedelta(days=1):
        weeks.append(week_label(monday))
        monday += timedelta(days=7)
    return weeks


def read_rows(xlsx_path):
    from openpyxl import load_workbook  # only needed here

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    header = next(it, ())
    idx = {name: i for i, name in enumerate(header)}
    for r in it:
        if r[idx["StockCode"]] is None or r[idx["InvoiceDate"]] is None:
            continue
        yield (
            r[idx["InvoiceNo"]], r[idx["StockCode"]], r[idx["Quantity"]],
            r[idx["InvoiceDate"]], r[idx["UnitPrice"]], r[idx["Description"]],
        )


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    out = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parent.parent / "data"
    rows, prices, descs = [], defaultdict(list), defaultdict(Counter)
    first = last = None
    for inv, code, qty, dt, price, desc in read_rows(argv[1]):
        first = dt if first is None or dt < first else first
        last = dt if last is None or dt > last else last
        rows.append((inv, code, qty, dt, price))
        if is_product_code(code) and price and price > 0:
            prices[str(code).strip()].append(float(price))
            if desc:
                descs[str(code).strip()][str(desc).strip()] += 1
    if first is None:
        sys.exit("no usable rows in the workbook")
    weeks = full_weeks(first, last)
    keep = set(weeks)
    net = {k: v for k, v in aggregate(rows).items() if k[0] in keep}
    nonzero = Counter()
    total = Counter()
    for (wk, code), units in net.items():
        if units > 0:
            nonzero[code] += 1
            total[code] += units
    ranked = sorted(nonzero, key=lambda c: (-nonzero[c], -total[c], c))[:TOP_SKUS]
    skus = sorted(ranked)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "weekly_demand.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["iso_week", "stock_code", "units"])
        for wk in weeks:
            for code in skus:
                w.writerow([wk, code, net.get((wk, code), 0)])
    with open(out / "sku_price.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["stock_code", "median_unit_price", "description"])
        for code in skus:
            desc = descs[code].most_common(1)[0][0].replace(",", " ")
            w.writerow([code, f"{median(prices[code]):.2f}", desc])
    for name in ("weekly_demand.csv", "sku_price.csv"):
        print(name, hashlib.sha256((out / name).read_bytes()).hexdigest())
    print("weeks", weeks[0], weeks[-1], len(weeks), "skus", len(skus))


if __name__ == "__main__":
    main(sys.argv)
