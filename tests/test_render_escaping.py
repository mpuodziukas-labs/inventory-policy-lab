"""SKU code and description are HTML-escaped everywhere the report prints them."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402

CODE, DESC = "C<&1", "D<&2"
ESC_CODE, ESC_DESC = "C&lt;&amp;1", "D&lt;&amp;2"


@pytest.fixture(scope="module")
def base():
    return pipeline.run()


@pytest.fixture
def html(base):
    res = copy.deepcopy(base)
    res["skus"][0].update(code=CODE, description=DESC, meets_target=False)
    return render.render_report(res)


@pytest.mark.parametrize("fragment,count", [
    (f"<td>{ESC_CODE}</td><td>{ESC_DESC}</td>", 2),  # SKU table and miss table
    (f"<title>{ESC_CODE}: ", 1),                      # dot chart circle title
    (f'class="tick">{ESC_CODE}</text>', 1),           # dot chart x label
])
def test_report_escapes_sku_code_and_description(html, fragment, count):
    assert html.count(fragment) == count
    assert CODE not in html
    assert DESC not in html
