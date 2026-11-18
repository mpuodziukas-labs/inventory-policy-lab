"""Rebuild every generated artefact: report, recommendation, result tables, README block."""
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402

START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def csv_text(rows, fields):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(fields)
    for r in rows:
        w.writerow([f"{r[k]:.4f}" if isinstance(r[k], float) else r[k] for k in fields])
    return out.getvalue()


def main():
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        sys.exit("README markers missing or not exactly one START before one END")
    res = pipeline.run()
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    outputs = {
        ROOT / "report" / "index.html": render.render_report(res),
        ROOT / "docs" / "recommendation.md": render.render_recommendation(res),
        ROOT / "results" / "sensitivity.csv": csv_text(
            res["sensitivity"],
            ["service_level", "z", "safety_stock_units", "safety_stock_holding_cost", "total_holding_cost"]),
        ROOT / "results" / "sku_policy.csv": csv_text(
            res["skus"],
            ["code", "mean_weekly", "sd_weekly", "eoq", "safety_stock", "reorder_point", "cycle_service_level",
             "fill_rate", "stockout_weeks_per_year", "avg_inventory", "turns", "wape_naive", "wape_ma",
             "wape_ses", "meets_target", "cause"]),
        readme: f"{head}{START}\n{render.render_readme_block(res)}{END}{tail}",
    }
    for path, content in outputs.items():
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("regen ok")


if __name__ == "__main__":
    main()
