"""Makefile targets run the scripts their names promise."""
import re
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


def test_regen_target_runs_regen_and_not_the_selftest():
    lines = recipe("regen")
    assert lines, "regen target has no recipe"
    assert any("lab/regen.py" in l for l in lines)
    assert not any("selftest" in l for l in lines)


def test_test_target_runs_the_whole_tests_folder():
    lines = recipe("test")
    assert len(lines) == 1
    assert re.fullmatch(r"\$\(PY\) -m pytest -q -p no:cacheprovider( tests/?)?", lines[0])


def test_python_command_can_be_overridden_from_the_environment():
    text = (ROOT / "Makefile").read_text().splitlines()
    assert "PY ?= python3" in text
    assert "PY = python3" not in text


def test_every_target_is_listed_as_phony():
    phony = [l for l in (ROOT / "Makefile").read_text().splitlines() if l.startswith(".PHONY:")]
    assert len(phony) == 1
    assert {"test", "selftest", "regen"} <= set(phony[0].split(":", 1)[1].split())


def test_selftest_target_does_not_swallow_a_failing_exit():
    lines = recipe("selftest")
    assert lines
    assert not any("||" in l or ";" in l or l.startswith("-") for l in lines)
