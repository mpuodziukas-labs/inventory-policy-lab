"""Edge cases for the simulation, root cause tie-break, series order and selftest."""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lab import pipeline, selftest  # noqa: E402
from lab.rootcause import decompose, dominant_cause  # noqa: E402
from policy import simulate as sim  # noqa: E402
from policy.formulas import safety_stock  # noqa: E402


class FixedRng:
    def __init__(self, u):
        self.u = u

    def random(self):
        return self.u


def test_draw_boundary_is_half_open():
    """u exactly at a cumulative probability belongs to the next value."""
    assert sim._draw(FixedRng(0.5), [1, 2], [0.5, 0.5]) == 2
    assert sim._draw(FixedRng(0.4999), [1, 2], [0.5, 0.5]) == 1


def test_orders_in_flight_at_the_end_are_not_counted():
    """Constant demand 10, lead 1, s=5, Q=50, no warm-up: orders fire at the end
    of weeks 5, 11, 17. Over 11 weeks the week-11 order arrives in week 12, after
    the window, so only the week-5 order is a completed cycle. It meets a shortage
    in week 6, so service is 0 and one order is counted."""
    out = sim.simulate([10], 5, 50, [1], [1.0], 1, 11, 0)
    assert out["orders"] == 1
    assert out["cycle_service_level"] == 0.0


def test_dominant_cause_tie_goes_to_demand():
    shares = decompose(1, 1.0, 1.0, 1.0)
    assert shares == (0.5, 0.5)
    assert dominant_cause(*shares) == "demand variability"
    assert dominant_cause(0.4, 0.6) == "lead-time variability"


def test_series_are_loaded_in_sorted_code_order(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "weekly_demand.csv").write_text(
        "iso_week,stock_code,units\n"
        "2011-W01,30000,1\n2011-W01,10000,2\n2011-W02,30000,3\n2011-W02,10000,4\n"
    )
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    series = pipeline.load_series()
    assert list(series) == ["10000", "30000"]
    assert series["10000"] == [2, 4]


def test_service_check_tolerance_is_pinned():
    def results(mean):
        return {"summary": {"mean_service_level": mean, "target": 0.95, "tolerance": 0.03}}

    assert selftest.service_check(results(0.9201))
    assert not selftest.service_check(results(0.9199))
    assert not selftest.service_check(results(0.5))


def test_selftest_does_not_flag_a_correct_formula_as_a_caught_fault():
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = selftest.run(planted_fn=safety_stock)
    assert code == 1
    assert "planted fault caught (check red): False" in buf.getvalue()
