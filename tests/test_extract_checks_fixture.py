"""The extract script's output passes the data-quality checks on a small fixture. No network, nothing written to data/."""
import csv
import importlib.util
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline  # noqa: E402

MON = datetime(2011, 1, 3, 0, 0)
SUN_NOON = datetime(2011, 1, 16, 12, 0)
W1, W2 = datetime(2011, 1, 4, 10), datetime(2011, 1, 11, 10)


def load():
    spec = importlib.util.spec_from_file_location("make_extract_fixture", ROOT / "scripts" / "make_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_output_passes_the_data_quality_checks_on_a_small_fixture(tmp_path, monkeypatch):
    rows = [
        ("S0", "POST", 1, MON, 1.0, "post"), ("S1", "POST", 1, SUN_NOON, 1.0, "post"),  # spans two full weeks
        ("A1", "11111", 10, W1, 2.0, "red bag"), ("A2", "11111", 5, W2, 2.0, "red bag"),
        ("C3", "11111", -3, W2, 2.0, "red bag"),                       # cancellation nets to 2 in W02
        ("A4", "22222B", 7, W1, 4.0, "blue mug"), ("A5", "22222B", 1, W2, 6.0, "blue mug"),
        ("A6", "33333", 9, W1, 0.0, "free gift"),                      # zero price: dropped
        ("A7", "DOT", 4, W1, 1.0, "postage"),                          # service code: dropped
        ("C8", "44444", -5, W1, 1.0, "cancel only"),                   # cancellation only: floored to 0
    ]
    m = load()
    monkeypatch.setattr(m, "read_rows", lambda path: iter(rows))
    m.main(["x", "ignored.xlsx", str(tmp_path)])

    with open(tmp_path / "weekly_demand.csv", newline="") as f:
        demand = list(csv.DictReader(f))
    assert list(demand[0].keys()) == ["iso_week", "stock_code", "units"]
    skus = sorted({r["stock_code"] for r in demand})
    weeks = sorted({r["iso_week"] for r in demand})
    assert skus == ["11111", "22222B"]
    assert weeks == ["2011-W01", "2011-W02"]
    assert len(demand) == len(skus) * len(weeks), "grid is not complete"
    assert all(re.fullmatch(r"\d{5}[A-Za-z]{0,2}", s) for s in skus)
    assert all(re.fullmatch(r"\d{4}-W\d{2}", w) for w in weeks)
    assert all(r["units"].isdigit() for r in demand)
    assert [r["iso_week"] for r in demand] == sorted(r["iso_week"] for r in demand)
    got = {(r["iso_week"], r["stock_code"]): int(r["units"]) for r in demand}
    assert got == {("2011-W01", "11111"): 10, ("2011-W02", "11111"): 2,
                   ("2011-W01", "22222B"): 7, ("2011-W02", "22222B"): 1}

    with open(tmp_path / "sku_price.csv", newline="") as f:
        prices = {r["stock_code"]: r for r in csv.DictReader(f)}
    assert sorted(prices) == skus
    assert float(prices["11111"]["median_unit_price"]) == 2.0
    assert float(prices["22222B"]["median_unit_price"]) == 5.0  # median of 4.0 and 6.0

    # the same files load through the pipeline's own loaders
    (tmp_path / "data").mkdir()
    for name in ("weekly_demand.csv", "sku_price.csv"):
        (tmp_path / "data" / name).write_bytes((tmp_path / name).read_bytes())
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    assert pipeline.load_series() == {"11111": [10, 2], "22222B": [7, 1]}
    assert set(pipeline.load_prices()) == {"11111", "22222B"}
