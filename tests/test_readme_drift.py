"""The README Results block must equal what the generator produces."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402

START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def block(text):
    return text.split(START, 1)[1].split(END, 1)[0].strip("\n") + "\n"


def readme_matches(text, res):
    return block(text) == render.render_readme_block(res)


def test_readme_results_block_equals_generated():
    res = pipeline.run()
    assert readme_matches((ROOT / "README.md").read_text(), res)


def test_drift_detector_has_teeth():
    res = pipeline.run()
    text = (ROOT / "README.md").read_text()
    changed = text.replace("SKUs meeting target | 31", "SKUs meeting target | 32")
    assert changed != text
    assert not readme_matches(changed, res)
