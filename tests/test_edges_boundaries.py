"""Boundary and fallback behaviours pinned one by one."""
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import pipeline, regen, render, selftest  # noqa: E402
from policy import simulate as sim  # noqa: E402
from policy.formulas import safety_stock  # noqa: E402

START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


class _Rng:
    def __init__(self, u):
        self.u = u

    def random(self):
        return self.u


def test_draw_falls_back_to_last_value_when_probs_sum_below_one():
    assert sim._draw(_Rng(0.99), [1, 2, 3], [0.1, 0.2, 0.3]) == 3


def test_order_raises_on_order_by_the_full_order_quantity(monkeypatch):
    """After an order is placed the position rises by Q, so the reorder loop ends
    after one order per cycle. A bounded draw counter fails fast instead of hanging."""
    calls = []

    real = sim._draw

    def counted(rng, values, probs):
        calls.append(1)
        assert len(calls) <= 30, "reorder loop did not end after the order raised on_order"
        return real(rng, values, probs)

    monkeypatch.setattr(sim, "_draw", counted)
    out = sim.simulate([10], 5, 50, [1], [1.0], 1, 60, 6)
    assert out["orders"] == 10
    assert len(calls) <= 12


def test_moving_average_of_short_history_divides_by_its_length():
    assert fc.moving_average([2, 4], 5) == 3.0


def test_mae_and_wape_non_finite_errors_name_their_measure():
    with pytest.raises(ValueError, match="MAE"):
        fc.mae([1.0], [math.nan])
    with pytest.raises(ValueError, match="WAPE"):
        fc.wape([1.0], [math.inf])


def test_lead_time_mean_and_sd_are_probability_weighted(monkeypatch):
    cfg = pipeline.load_config()
    cfg["lead_time_weeks"] = {"values": [1, 2, 3], "probs": [0.6, 0.3, 0.1]}
    monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
    s = pipeline.run()["summary"]
    assert s["lead_mean"] == pytest.approx(1.5)
    assert s["lead_sd"] == pytest.approx(math.sqrt(0.6 * 0.25 + 0.3 * 0.25 + 0.1 * 2.25))
    assert s["protect"] == pytest.approx(1.5 + cfg["review_period_weeks"])


def test_ses_beats_naive_does_not_count_ties(monkeypatch):
    monkeypatch.setattr(pipeline.fc, "naive_forecast", lambda h: h[-1])
    monkeypatch.setattr(pipeline.fc, "ses", lambda h, alpha: h[-1])
    s = pipeline.run()["summary"]
    assert s["ses_beats_naive"] == 0


def test_service_check_meets_target_at_exactly_target_minus_tolerance():
    res = {"summary": {"mean_service_level": 0.75, "target": 1.0, "tolerance": 0.25}}
    assert selftest.service_check(res) is True
    res["summary"]["mean_service_level"] = 0.5
    assert selftest.service_check(res) is False


def test_selftest_runs_as_a_script_from_another_directory(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run([sys.executable, str(ROOT / "lab" / "selftest.py")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "planted fault caught (check red): True" in p.stdout.splitlines()


def test_selftest_injects_the_planted_fault_and_clean_control_is_green(capsys):
    assert selftest.run() == 0
    out = capsys.readouterr().out.splitlines()
    assert "correct formula check green: True" in out
    assert "planted fault caught (check red): True" in out
    # the correct formula passed as the "fault" is not red, so the run fails
    assert selftest.run(planted_fn=safety_stock) == 1
    out = capsys.readouterr().out.splitlines()
    assert "planted fault caught (check red): False" in out


@pytest.mark.parametrize("body", [f"a\n{START}\nb\n", f"a\n{END}\nb\n", "a\nb\n"])
def test_regen_rejects_readme_missing_a_marker_and_leaves_it_unchanged(tmp_path, monkeypatch, body):
    readme = tmp_path / "README.md"
    readme.write_text(body)
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="README markers missing"):
        regen.main()
    assert readme.read_text() == body


def test_regen_prints_regen_ok_as_its_last_line(tmp_path, monkeypatch, capsys):
    (tmp_path / "README.md").write_text(f"top\n{START}\nold\n{END}\nbottom\n")
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    regen.main()
    assert capsys.readouterr().out.splitlines()[-1] == "regen ok"


def test_report_escapes_sku_description():
    res = pipeline.run()
    res["skus"][0]["description"] = "zz<b>&"
    html = render.render_report(res)
    assert "<td>zz&lt;b&gt;&amp;</td>" in html
    assert "zz<b>" not in html
