"""A bad config is rejected up front, and a failed regen leaves every published file as it was."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402

PUBLISHED = ("report/index.html", "docs/recommendation.md", "results/sensitivity.csv", "results/sku_policy.csv")


def _stub_sim(history, rop, q, lv, lp, seed, weeks, warmup):
    return {"cycle_service_level": 1.0, "fill_rate": 1.0, "stockout_weeks_per_year": 0.0,
            "avg_inventory": 1.0, "turns": 1.0, "orders": 1}


@pytest.fixture
def stage(tmp_path, monkeypatch):
    """A scratch copy of the lab with stale published files; the repo itself is never written."""
    def go(**overrides):
        shutil.copytree(ROOT / "data", tmp_path / "data")
        shutil.copy(ROOT / "README.md", tmp_path / "README.md")
        cfg = dict(json.loads((ROOT / "config.json").read_text()), **overrides)
        (tmp_path / "config.json").write_text(json.dumps(cfg))
        for p in PUBLISHED:
            f = tmp_path / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("stale")
        monkeypatch.setattr(regen, "ROOT", tmp_path)
        monkeypatch.setattr(pipeline, "ROOT", tmp_path)
        monkeypatch.setattr(pipeline, "simulate", _stub_sim)
        return tmp_path
    return go


def _untouched(d):
    assert (d / "README.md").read_bytes() == (ROOT / "README.md").read_bytes()
    for p in PUBLISHED:
        assert (d / p).read_text() == "stale", p


@pytest.mark.parametrize("overrides, message", [
    ({"service_levels": [0.9, 0.975, 0.99]}, "service_levels must include the service target 0.95"),
    ({"service_levels": [0.9, 0.95, 0.99]},
     "service_levels must include 0.95 and 0.975, the two levels the report compares"),
    ({"service_target": 0.3, "service_levels": [0.3, 0.95, 0.975]},
     "service target and service levels must be at least 0.5 and below 1"),
    ({"service_levels": [0.95, 0.975, 1.0]},
     "service target and service levels must be at least 0.5 and below 1"),
    ({"service_levels": [0.4, 0.95, 0.975]},
     "service target and service levels must be at least 0.5 and below 1"),
    ({"tolerance": -0.01}, "tolerance must be finite and not negative"),
    ({"tolerance": float("nan")}, "tolerance must be finite and not negative"),
    ({"ses_alpha": 0}, "ses_alpha must be above 0 and at most 1"),
    ({"ses_alpha": 1.5}, "ses_alpha must be above 0 and at most 1"),
    ({"ses_alpha": float("nan")}, "ses_alpha must be above 0 and at most 1"),
    ({"sim_weeks": 5200.0}, "sim_weeks must be a whole number"),
    ({"sim_weeks": True}, "sim_weeks must be a whole number"),
    ({"sim_warmup_weeks": 52.0}, "sim_warmup_weeks must be a whole number"),
    ({"sim_warmup_weeks": 1.5}, "sim_warmup_weeks must be a whole number"),
])
def test_regen_with_a_bad_config_raises_and_leaves_every_published_file_untouched(stage, overrides, message):
    d = stage(**overrides)
    with pytest.raises(ValueError, match=message):
        regen.main()
    _untouched(d)


@pytest.mark.parametrize("name", ["render_report", "render_recommendation", "render_readme_block"])
def test_regen_renders_everything_before_it_writes_anything(stage, monkeypatch, name):
    d = stage()

    def boom(res):
        raise RuntimeError("render failed")

    monkeypatch.setattr(regen.render, name, boom)
    with pytest.raises(RuntimeError, match="render failed"):
        regen.main()
    _untouched(d)


def test_regen_with_a_good_config_writes_every_published_file(stage, capsys):
    d = stage()
    regen.main()
    for p in PUBLISHED:
        assert (d / p).read_text() != "stale", p
    assert capsys.readouterr().out.splitlines()[-1] == "regen ok"


def test_the_committed_config_is_valid():
    pipeline.validate_config(pipeline.load_config())


@pytest.mark.parametrize("overrides", [
    {"ses_alpha": 1}, {"ses_alpha": 1.0}, {"ses_alpha": 0.0001}, {"tolerance": 0}, {"sim_warmup_weeks": 0},
    {"service_target": 0.5, "service_levels": [0.5, 0.95, 0.975]},
    {"service_target": 0.999, "service_levels": [0.95, 0.975, 0.999]},
])
def test_boundary_values_of_the_config_are_accepted(overrides):
    pipeline.validate_config(dict(pipeline.load_config(), **overrides))


def test_no_sku_reaches_simulate_with_a_negative_reorder_point_at_the_lowest_allowed_target(stage, monkeypatch):
    stage(service_target=0.5, service_levels=[0.5, 0.95, 0.975])
    seen = []

    def spy(history, rop, *rest):
        seen.append(rop)
        return _stub_sim(history, rop, *rest)

    monkeypatch.setattr(pipeline, "simulate", spy)
    pipeline.run()
    assert len(seen) == 40
    assert min(seen) >= 0
