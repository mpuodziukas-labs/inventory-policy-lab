"""The report cells match the results table, and regen rewrites every output in full."""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen, render  # noqa: E402

_cache = {}


def fresh_html():
    if "html" not in _cache:
        _cache["html"] = render.render_report(pipeline.run())
    return _cache["html"]


def csv_rows():
    with open(ROOT / "results" / "sku_policy.csv", newline="") as f:
        return list(csv.DictReader(f))


def policy_table_rows(html):
    section = html.split("<h2>Policy, KPIs and forecast error per SKU</h2>", 1)[1]
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", section, re.S):
        cells = re.findall(r"<td>(.*?)</td>", tr)
        if cells:
            out.append(cells)
    return out


def pct_cell(cell):
    return float(cell.rstrip("%")) / 100


def test_policy_table_cells_match_results_csv():
    rows, expected = policy_table_rows(fresh_html()), csv_rows()
    assert len(rows) == len(expected) == 40
    for cells, e in zip(rows, expected):
        assert cells[0] == e["code"]
        assert abs(pct_cell(cells[6]) - float(e["cycle_service_level"])) <= 0.0006
        assert abs(pct_cell(cells[7]) - float(e["fill_rate"])) <= 0.0006
        assert abs(float(cells[8]) - float(e["stockout_weeks_per_year"])) <= 0.051
        assert abs(float(cells[10]) - float(e["turns"])) <= 0.051


def test_kpi_tile_counts_skus_meeting_target():
    m = re.search(r"<b>(\d+) of (\d+)</b>SKUs meeting", fresh_html())
    assert m
    rows = csv_rows()
    assert int(m.group(1)) == sum(1 for r in rows if r["meets_target"] == "True")
    assert int(m.group(2)) == len(rows)


def test_dot_chart_keeps_target_line_and_every_dot_inside_the_plot():
    svg = fresh_html().split("<svg", 1)[1].split("</svg>", 1)[0]
    top, bottom = 16.0, 300 - 70
    target = re.search(r'y1="([\d.\-]+)" y2="[\d.\-]+" class="target"', svg)
    assert target and top <= float(target.group(1)) <= bottom
    ys = [float(v) for v in re.findall(r'<circle cx="[\d.]+" cy="([\d.\-]+)"', svg)]
    assert len(ys) == 40 and all(top <= v <= bottom for v in ys)
    assert ">100%<" in svg


def test_regen_rewrites_every_output_in_full(tmp_path, monkeypatch):
    committed = {p: (ROOT / p).read_bytes() for p in (
        "report/index.html", "docs/recommendation.md", "results/sensitivity.csv",
        "results/sku_policy.csv", "README.md")}
    for p in committed:
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("stale")
    readme = ROOT / "README.md"
    (tmp_path / "README.md").write_bytes(readme.read_bytes().replace(b"Forecast backtest", b"STALE backtest", 1))
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    regen.main()
    for p, data in committed.items():
        assert (tmp_path / p).read_bytes() == data, p
    lines = (tmp_path / "results" / "sku_policy.csv").read_text().splitlines()
    assert len(lines) == 41
    assert re.fullmatch(r"\d+\.\d{4}", lines[1].split(",")[1])
