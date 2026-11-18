"""Hand-worked exact numbers: simulation stockout window, one-point exponential smoothing, selftest lines and exits."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast as fc  # noqa: E402
from lab import selftest  # noqa: E402
from policy.simulate import simulate  # noqa: E402


def test_stockout_weeks_are_counted_over_weeks_one_to_total():
    """History [3], reorder point 0, order 3, lead 1 week, 4 weeks, no warm-up.
    Week 1: 3 sold, stock 0, order placed. Week 2: nothing to sell (short), the order lands. Week 3: sold, order.
    Week 4: short, the order lands. Short weeks 2 and 4, so 2 / 4 * 52 = 26. Demanded 12, short 6, fill 0.5.
    Stock after each week 0, 3, 0, 3, so average 6 / 4 = 1.5 and turns 3 * 52 / 1.5 = 104.
    Orders placed in weeks 1 and 3 both complete by week 4; both windows hold a short week, so service 0."""
    assert simulate([3], 0, 3, [1], [1.0], 1, 4, 0) == {
        "cycle_service_level": 0.0, "fill_rate": 0.5, "stockout_weeks_per_year": 26.0,
        "avg_inventory": 1.5, "turns": 104.0, "orders": 2}


def test_stockout_weeks_in_a_two_value_history_with_variable_lead():
    assert simulate([0, 10], 0, 1, [1, 2], [0.5, 0.5], 1, 6, 0)["stockout_weeks_per_year"] == 17.333333333333332


def test_ses_of_a_one_week_history_is_that_week_exactly():
    # 0.3 * 3 + 0.7 * 3 is 2.9999999999999996 in floats; the first week is the start level, not a blended value
    assert fc.ses([3], 0.3) == 3
    assert fc.ses([0.1], 0.3) == 0.1


def test_ses_hand_worked_three_weeks():
    # level 10; then 0.5 * 20 + 0.5 * 10 = 15; then 0.5 * 40 + 0.5 * 15 = 27.5
    assert fc.ses([10, 20, 40], 0.5) == 27.5


# ---- selftest

def _run_with(monkeypatch, outcomes, capsys):
    from lab import pipeline

    monkeypatch.setattr(pipeline, "run", lambda safety_stock_fn=None: {})
    seq = iter(outcomes)
    monkeypatch.setattr(selftest, "service_check", lambda results: next(seq))
    code = selftest.run()
    return code, capsys.readouterr().out.splitlines()


def test_selftest_prints_the_control_flag_on_the_control_line_and_the_fault_flag_on_the_fault_line(
        monkeypatch, capsys):
    code, lines = _run_with(monkeypatch, [False, False], capsys)
    assert code == 1
    assert lines == ["correct formula check green: False", "planted fault caught (check red): True"]
    code, lines = _run_with(monkeypatch, [True, True], capsys)
    assert code == 1
    assert lines == ["correct formula check green: True", "planted fault caught (check red): False"]
    code, lines = _run_with(monkeypatch, [True, False], capsys)
    assert code == 0
    assert lines == ["correct formula check green: True", "planted fault caught (check red): True"]


@pytest.fixture
def tree(tmp_path):
    for d in ("lab", "policy", "data"):
        shutil.copytree(ROOT / d, tmp_path / d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    return tmp_path


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _script(tree):
    return subprocess.run([sys.executable, str(tree / "lab" / "selftest.py")], capture_output=True, text=True,
                          cwd=tree)


def test_selftest_script_exits_zero_on_the_committed_tree(tree):
    p = _script(tree)
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == ["correct formula check green: True", "planted fault caught (check red): True"]


def test_selftest_script_exits_one_when_the_control_check_is_red(tree):
    _edit(tree / "lab" / "selftest.py", "return s[\"mean_service_level\"] >=", "return False and s[\"mean_service_level\"] >=")
    p = _script(tree)
    assert p.returncode == 1
    assert p.stdout.splitlines() == ["correct formula check green: False", "planted fault caught (check red): True"]


def test_selftest_script_exits_one_when_the_planted_fault_is_not_caught(tree):
    _edit(tree / "lab" / "selftest.py", "return z * math.sqrt(sigma_d**2 + mean_d**2 * sigma_l**2)",
          "return z * math.sqrt(lead_time * sigma_d**2 + mean_d**2 * sigma_l**2)")
    p = _script(tree)
    assert p.returncode == 1
    assert p.stdout.splitlines() == ["correct formula check green: True", "planted fault caught (check red): False"]
