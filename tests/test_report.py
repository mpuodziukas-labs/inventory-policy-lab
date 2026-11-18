"""The report is one self-contained file and the recommendation quotes regenerated numbers."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402


def test_report_is_static_and_self_contained():
    html = (ROOT / "report" / "index.html").read_text()
    assert "<svg" in html
    assert not re.search(r"<script", html, re.I)
    assert not re.search(r"https?://", html)
    assert not re.search(r"""(src|href)\s*=""", html, re.I)
    assert "@import" not in html and "url(" not in html


def test_recommendation_matches_regenerated_numbers():
    res = pipeline.run()
    committed = (ROOT / "docs" / "recommendation.md").read_text()
    assert committed == render.render_recommendation(res)
    s = res["summary"]
    assert f"{s['meeting_target']} of {s['sku_count']} SKUs meet target" in committed
