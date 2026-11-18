import csv
import hashlib
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_extract():
    spec = importlib.util.spec_from_file_location(
        "make_extract", ROOT / "scripts" / "make_extract.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_product_code_filter():
    m = load_extract()
    for ok in ("85123A", "22423", "85099B", "23166"):
        assert m.is_product_code(ok), ok
    for bad in ("POST", "DOT", "M", "BANK CHARGES", "D", "S", "C2", "PADS",
                "AMAZONFEE", "CRUK", "gift_0001_10"):
        assert not m.is_product_code(bad), bad


def test_week_label_is_iso():
    from datetime import datetime

    m = load_extract()
    assert m.week_label(datetime(2010, 12, 1, 8, 26)) == "2010-W48"
    assert m.week_label(datetime(2011, 1, 3, 9, 0)) == "2011-W01"


def test_aggregate_nets_cancellations_and_excludes_noise():
    """Hand-worked: SKU 11111 week W10 has sales 10 and 5, a cancellation of
    -3 on a C invoice -> 12. SKU 22222 has only a cancellation of -5 -> floored
    to 0. A zero-price row, a non-C negative row and POST are excluded."""
    from datetime import datetime

    m = load_extract()
    d = datetime(2011, 3, 8)
    rows = [
        ("1", "11111", 10, d, 1.0),
        ("2", "11111", 5, d, 1.0),
        ("C3", "11111", -3, d, 1.0),
        ("C4", "22222", -5, d, 1.0),
        ("5", "33333", 7, d, 0.0),
        ("6", "33333", -2, d, 1.0),
        ("7", "POST", 4, d, 1.0),
    ]
    out = m.aggregate(rows)
    assert out[("2011-W10", "11111")] == 12
    assert out.get(("2011-W10", "22222"), 0) == 0
    assert ("2011-W10", "33333") not in out
    assert ("2011-W10", "POST") not in out


def test_weekly_demand_checks():
    path = ROOT / "data" / "weekly_demand.csv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows, "empty extract"
    assert list(rows[0].keys()) == ["iso_week", "stock_code", "units"]
    skus = sorted({r["stock_code"] for r in rows})
    weeks = sorted({r["iso_week"] for r in rows})
    assert len(skus) == 40
    assert len(rows) == 40 * len(weeks), "grid is not complete"
    assert all(re.fullmatch(r"\d{5}[A-Za-z]{0,2}", s) for s in skus)
    assert all(re.fullmatch(r"\d{4}-W\d{2}", w) for w in weeks)
    assert all(r["units"].isdigit() for r in rows), "negative or non-integer units"
    assert weeks == sorted(weeks)
    assert len(weeks) >= 50
    nonzero = {s: 0 for s in skus}
    for r in rows:
        if int(r["units"]) > 0:
            nonzero[r["stock_code"]] += 1
    assert min(nonzero.values()) >= len(weeks) * 0.8


def test_sku_price_covers_every_sku_with_positive_price():
    with open(ROOT / "data" / "weekly_demand.csv", newline="") as f:
        skus = {r["stock_code"] for r in csv.DictReader(f)}
    with open(ROOT / "data" / "sku_price.csv", newline="") as f:
        prices = {r["stock_code"]: float(r["median_unit_price"]) for r in csv.DictReader(f)}
    assert set(prices) == skus
    assert all(p > 0 for p in prices.values())


def test_source_note_hash_matches_vendored_csv():
    note = (ROOT / "data" / "SOURCE.md").read_text()
    for name in ("weekly_demand.csv", "sku_price.csv"):
        digest = hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest()
        assert digest in note, name
    assert "f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b" in note
    assert "10.24432/C5BW33" in (ROOT / "data" / "LICENSE-dataset.txt").read_text()
