"""The SPEC trace table must be honest: PROVEN and PARTIAL rows name real tests, GAP rows name none."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def trace_rows():
    text = (ROOT / "SPEC.md").read_text()
    section = text.split("## Requirement to test trace", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[-1] in ("PROVEN", "PARTIAL", "GAP"):
            rows.append(cells)
    return rows


def test_trace_has_both_kinds_of_row():
    statuses = {r[-1] for r in trace_rows()}
    assert statuses == {"PROVEN", "PARTIAL", "GAP"}


def test_every_proven_row_names_existing_test_functions():
    checked = 0
    for req, _seen, _file, ids, status in trace_rows():
        if status not in ("PROVEN", "PARTIAL"):
            continue
        for tid in [t.strip() for t in ids.split(",")]:
            assert "::" in tid, f"{req}: malformed test id {tid!r}"
            path, func = tid.split("::")
            f = ROOT / path
            assert f.is_file(), f"{req}: missing file {path}"
            assert re.search(rf"^def {re.escape(func)}\(", f.read_text(), re.M), f"{req}: no {func} in {path}"
            checked += 1
    assert checked > 0


def test_every_gap_row_names_no_test():
    for req, _seen, _file, ids, status in trace_rows():
        if status == "GAP":
            assert ids == "none", f"{req}: GAP row names a test"


def test_stakeholders_row_stays_a_gap():
    row = next(r for r in trace_rows() if r[0].startswith("Stakeholders"))
    assert row[-1] == "GAP"
