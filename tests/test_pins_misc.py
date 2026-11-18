"""Pins from the mutation review: messages, ties, write order, CI shape, fetch timeout, documented config."""
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import forecast, pipeline, regen, rootcause, selftest  # noqa: E402


def test_the_empty_test_window_message_is_exact():
    with pytest.raises(ValueError) as err:
        forecast.mae([], [])
    assert str(err.value) == "MAE is undefined: no test weeks (the series is no longer than the training minimum)"


def test_a_one_ulp_lead_for_lead_time_still_wins_the_tie_break():
    """0.5 against the next double above 0.5: lead time is larger, so it is the dominant cause."""
    above = math.nextafter(0.5, 1.0)
    assert rootcause.dominant_cause(0.5, above) == "lead-time variability"
    assert rootcause.dominant_cause(above, 0.5) == "demand variability"
    assert rootcause.dominant_cause(0.5, 0.5) == "demand variability"


def test_the_planted_fault_ignores_lead_time_even_when_it_is_infinite():
    """The fault must not multiply by anything built from lead_time: inf would turn the answer into nan."""
    got = selftest.safety_stock_dropped_scaling(1.0, math.inf, 2.0, 3.0, 0.5)
    assert got == math.sqrt(2.0**2 + 3.0**2 * 0.5**2)


def test_selftest_reports_the_planted_fault_as_not_caught_when_the_control_is_red(monkeypatch, capsys):
    """Control red (first check False) and planted check green (second True): caught must print False."""
    answers = iter([False, True])
    monkeypatch.setattr(pipeline, "run", lambda **kw: {})
    monkeypatch.setattr(selftest, "service_check", lambda results: next(answers))
    assert selftest.run() == 1
    assert capsys.readouterr().out == (
        "correct formula check green: False\nplanted fault caught (check red): False\n")


def test_selftest_exits_zero_only_when_the_control_is_green_and_the_fault_is_caught(monkeypatch, capsys):
    answers = iter([True, False])
    monkeypatch.setattr(pipeline, "run", lambda **kw: {})
    monkeypatch.setattr(selftest, "service_check", lambda results: next(answers))
    assert selftest.run() == 0
    assert capsys.readouterr().out == (
        "correct formula check green: True\nplanted fault caught (check red): True\n")


def test_regen_renders_everything_before_writing_the_readme(tmp_path, monkeypatch):
    """A failing write to report/ must leave the README exactly as it was."""
    readme = tmp_path / "README.md"
    original = f"top\n{regen.START}\nold\n{regen.END}\nbottom\n"
    readme.write_text(original, encoding="utf-8")
    (tmp_path / "report").write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    with pytest.raises(OSError):
        regen.main()
    assert readme.read_text(encoding="utf-8") == original


def ci_lines():
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").splitlines()


def test_ci_checks_out_the_repo_before_any_run_step():
    lines = ci_lines()
    checkout = next(i for i, l in enumerate(lines) if re.match(r"\s*-\s*uses:\s*actions/checkout@v\d+\s*$", l))
    first_run = next(i for i, l in enumerate(lines) if re.match(r"\s*-\s*run:", l))
    assert checkout < first_run


def test_the_fetch_script_gives_the_download_a_120_second_timeout(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("fetch_data_timeout", ROOT / "scripts" / "fetch_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    blob = b"PK pretend"
    seen = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return blob

    def fake_urlopen(url, timeout=None):
        seen.append(timeout)
        return Resp()

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(m, "SHA256", hashlib.sha256(blob).hexdigest())
    m.main(["fetch_data.py", str(tmp_path / "dl")])
    assert seen == [120]


def test_config_json_holds_exactly_the_values_spec_md_documents():
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    block = re.search(r"<!-- CONFIG-VALUES:START -->\s*```json\n(.*?)\n```\s*<!-- CONFIG-VALUES:END -->", spec, re.S)
    assert block, "SPEC.md has no config values block"
    documented = json.loads(block.group(1))
    actual = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert documented == actual
    assert actual["tolerance"] == 0.03
