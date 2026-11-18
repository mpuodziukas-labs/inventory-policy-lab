"""Makefile targets run the scripts their names promise."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def recipe(target):
    lines, inside = [], False
    for line in (ROOT / "Makefile").read_text().splitlines():
        if line.startswith(f"{target}:"):
            inside = True
        elif inside and line.startswith("\t"):
            lines.append(line.strip())
        elif inside:
            break
    return lines


def test_selftest_target_runs_the_selftest_and_not_regen():
    lines = recipe("selftest")
    assert lines, "selftest target has no recipe"
    assert any("lab/selftest.py" in l for l in lines)
    assert not any("regen" in l for l in lines)
