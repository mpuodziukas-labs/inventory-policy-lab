"""Rendered text counts SKUs from the summary, never from a fixed number."""
import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402


@pytest.fixture(scope="module")
def three():
    res = copy.deepcopy(pipeline.run())
    res["summary"]["sku_count"] = 3
    return res


def test_readme_block_uses_the_summary_sku_count(three):
    text = render.render_readme_block(three)
    assert "| Method | WAPE, all 3 SKUs |" in text
    assert "Service level sensitivity (all 3 SKUs," in text
    assert not re.search(r"\b40 SKUs", text)


def test_recommendation_uses_the_summary_sku_count(three):
    text = render.render_recommendation(three)
    assert "Moving all 3 SKUs from" in text
    assert not re.search(r"\b40 SKUs", text)


def test_report_intro_uses_the_summary_sku_count(three):
    html = render.render_report(three)
    assert "<p>3 SKUs, " in html
    assert not re.search(r"\b40 SKUs", html)
