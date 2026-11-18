"""README marker handling in regen: exactly one START before exactly one END, nothing written otherwise."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import regen  # noqa: E402

START, END = regen.START, regen.END

BAD = {
    "reversed": f"top\n{END}\nmid\n{START}\nbottom\n",
    "start_twice": f"top\n{START}\na\n{START}\nb\n{END}\nbottom\n",
    "end_twice": f"top\n{START}\na\n{END}\nb\n{END}\nbottom\n",
    "start_missing": f"top\n{END}\nbottom\n",
    "end_missing": f"top\n{START}\nbottom\n",
    "both_missing": "top\nbottom\n",
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_regen_rejects_bad_markers_cleanly_and_writes_nothing(tmp_path, monkeypatch, name):
    readme = tmp_path / "README.md"
    readme.write_text(BAD[name])
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="README markers missing") as exc:
        regen.main()
    assert exc.value.code != 0
    assert readme.read_text() == BAD[name]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["README.md"]


def test_regen_replaces_only_the_block_and_keeps_surrounding_text(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text(f"top\n{START}\nold\n{END}\nbottom\n")
    monkeypatch.setattr(regen, "ROOT", tmp_path)
    regen.main()
    got = readme.read_text()
    assert got.startswith(f"top\n{START}\n")
    assert got.endswith(f"{END}\nbottom\n")
    assert "\nold\n" not in got
