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


CI = ROOT / ".github" / "workflows" / "ci.yml"


def ci_runs():
    return [m.group(1).strip() for m in re.finditer(r"^\s*-?\s*run:\s*(.+)$", CI.read_text(), re.M)]


def test_ci_runs_on_push_and_pull_request():
    text = CI.read_text()
    triggers = re.search(r"^on:(.*?)^jobs:", text, re.M | re.S).group(1)
    assert re.search(r"\bpush\b", triggers)
    assert re.search(r"\bpull_request\b", triggers)


def test_ci_runs_on_ubuntu():
    assert re.findall(r"^\s*runs-on:\s*(\S+)", CI.read_text(), re.M) == ["ubuntu-latest"]


def test_ci_python_is_at_least_3_10():
    """Neither the README nor the SPEC states a Python version, so 3.10 is the floor."""
    versions = re.findall(r'python-version:\s*"?(\d+)\.(\d+)', CI.read_text())
    assert len(versions) == 1
    assert tuple(map(int, versions[0])) >= (3, 10)


def test_ci_installs_pytest():
    assert any(re.fullmatch(r"(python3? -m )?pip install .*\bpytest\b.*", r) for r in ci_runs())


def test_ci_runs_the_full_suite_the_way_the_makefile_does():
    (make_line,) = recipe("test")
    expected = make_line.replace("$(PY)", "python3")
    assert expected in ci_runs() or "make test" in ci_runs()
    assert not any("-m pytest" in r and r != expected for r in ci_runs())


def test_ci_runs_the_selftest_and_does_not_swallow_its_exit():
    expected = recipe("selftest")[0].replace("$(PY)", "python3")
    assert "make selftest" in ci_runs() or expected in ci_runs()
    text = CI.read_text()
    assert "||" not in text
    assert "continue-on-error" not in text


def test_selftest_target_does_not_swallow_a_failing_exit():
    lines = recipe("selftest")
    assert lines
    assert not any("||" in l or ";" in l or l.startswith("-") for l in lines)
