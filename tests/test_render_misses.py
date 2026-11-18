"""The SKUs-that-miss-target sections of the report and the recommendation."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402


@pytest.fixture(scope="module")
def base():
    return pipeline.run()


def _all_meet(base):
    res = copy.deepcopy(base)
    for r in res["skus"]:
        r["meets_target"] = True
    return res


def _one_miss(base):
    res = _all_meet(base)
    res["skus"][0]["meets_target"] = False
    return res


def test_report_with_no_misses_has_an_empty_row_spanning_every_column(base):
    html = render.render_report(_all_meet(base))
    section = html.split("<h2>SKUs that miss target</h2>", 1)[1].split("<h2>", 1)[0]
    assert section.count("<th>") == 7
    assert "<tr><td colspan='7'>None</td></tr>" in section


def test_recommendation_with_no_misses_says_none_with_a_full_stop(base):
    text = render.render_recommendation(_all_meet(base))
    assert "## SKUs that miss target\n\nNone.\n\n## Cost of a higher target" in text


def test_recommendation_with_no_misses_renders_no_miss_table(base):
    text = render.render_recommendation(_all_meet(base))
    assert "| SKU |" not in text
    assert "fall short" not in text


def test_recommendation_with_a_miss_renders_the_table_and_count(base):
    text = render.render_recommendation(_one_miss(base))
    assert "1 SKUs fall short." in text
    assert "| SKU | Description |" in text
    assert "None." not in text


def test_recommendation_sensitivity_lookup_uses_the_exact_level(base):
    res = _all_meet(base)
    sens = [dict(r) for r in res["sensitivity"] if r["service_level"] != 0.975]
    template = next(r for r in res["sensitivity"] if r["service_level"] == 0.975)
    exact = dict(template, service_level=0.975, safety_stock_units=111111.0)
    near = dict(template, service_level=0.9754, safety_stock_units=222222.0)
    res["sensitivity"] = sens + [exact, near]  # near is listed last and must not shadow exact
    text = render.render_recommendation(res)
    assert "to 111,111 units" in text
    assert "222,222" not in text
