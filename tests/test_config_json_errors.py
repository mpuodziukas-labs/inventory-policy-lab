"""Bad config.json and README.md bytes get the right named error with the original cause attached."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, regen  # noqa: E402


def exact(text):
    return "^" + re.escape(text) + "$"


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    return tmp_path


def test_malformed_json_is_named_as_json_and_never_as_utf8(lab_dir):
    (lab_dir / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match=exact("config.json is not valid JSON")) as err:
        pipeline.load_config()
    assert "UTF-8" not in str(err.value)
    assert isinstance(err.value.__cause__, json.JSONDecodeError)


def test_an_invalid_utf8_config_keeps_the_decode_error_as_its_cause(lab_dir):
    (lab_dir / "config.json").write_bytes(b'{"seed": 1, "note": "\xff"}')
    with pytest.raises(ValueError, match=exact("config.json is not valid UTF-8")) as err:
        pipeline.load_config()
    assert isinstance(err.value.__cause__, UnicodeDecodeError)


def test_an_invalid_utf8_readme_keeps_the_decode_error_as_its_cause(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_bytes(b"top \xff\n")
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=exact("README.md is not valid UTF-8")) as err:
        regen.main()
    assert isinstance(err.value.__cause__, UnicodeDecodeError)


def test_a_readme_read_error_that_is_not_a_decode_error_is_not_called_invalid_utf8(monkeypatch):
    """A path with an embedded NUL makes the read raise a plain ValueError: it must pass through unrenamed."""
    monkeypatch.setattr(regen, "ROOT", Path("no\0such"))
    with pytest.raises(ValueError) as err:
        regen.main()
    assert "UTF-8" not in str(err.value)
    assert err.value.__cause__ is None


@pytest.mark.parametrize("weeks", [53, 60])
def test_review_period_has_no_upper_cap(weeks):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["review_period_weeks"] = weeks
    pipeline.validate_config(cfg)


def test_a_review_period_of_60_weeks_runs_and_widens_the_protection_interval(monkeypatch):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["review_period_weeks"] = 60
    monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
    assert pipeline.run()["summary"]["protect"] == 62.0
