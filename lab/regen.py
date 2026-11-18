"""Rebuild every generated artefact: report, recommendation, result tables, README block."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402

START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(fields)
        for r in rows:
            w.writerow([f"{r[k]:.4f}" if isinstance(r[k], float) else r[k] for k in fields])


def main():
    res = pipeline.run()
    (ROOT / "report").mkdir(exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "report" / "index.html").write_text(render.render_report(res))
    (ROOT / "docs" / "recommendation.md").write_text(render.render_recommendation(res))
    write_csv(ROOT / "results" / "sensitivity.csv", res["sensitivity"],
              ["service_level", "z", "safety_stock_units", "safety_stock_holding_cost", "total_holding_cost"])
    write_csv(ROOT / "results" / "sku_policy.csv", res["skus"],
              ["code", "mean_weekly", "sd_weekly", "eoq", "safety_stock", "reorder_point", "cycle_service_level",
               "fill_rate", "stockout_weeks_per_year", "avg_inventory", "turns", "wape_naive", "wape_ma",
               "wape_ses", "meets_target", "cause"])
    readme = ROOT / "README.md"
    text = readme.read_text()
    if START not in text or END not in text:
        sys.exit("README markers missing")
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    readme.write_text(f"{head}{START}\n{render.render_readme_block(res)}{END}{tail}")
    print("regen ok")


if __name__ == "__main__":
    main()
