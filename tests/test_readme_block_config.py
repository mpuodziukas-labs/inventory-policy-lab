"""The README block states the configuration it was given, not remembered defaults."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, render  # noqa: E402


@pytest.fixture(scope="module")
def block():
    res = copy.deepcopy(pipeline.run())
    res["config"].update(seed=777, min_train_weeks=13, sim_weeks=1234, ma_window=7, ses_alpha=0.55)
    return render.render_readme_block(res), res["summary"]["weeks"]


def test_block_shows_the_configured_minimum_training_weeks_and_test_weeks(block):
    text, weeks = block
    assert f"13 weeks minimum training, {weeks - 13} test weeks per SKU." in text


def test_block_shows_the_configured_seed(block):
    assert "seed 777)" in block[0]


def test_block_shows_the_configured_simulation_weeks(block):
    assert "(1234 weeks per SKU, seed" in block[0]


def test_block_shows_the_configured_moving_average_window(block):
    assert "| Moving average (7 weeks) |" in block[0]


def test_block_shows_the_configured_smoothing_alpha(block):
    assert "(alpha 0.55) |" in block[0]
