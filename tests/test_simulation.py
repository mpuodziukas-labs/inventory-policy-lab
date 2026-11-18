from policy.simulate import simulate

BOOT = [3, 8, 0, 12, 5, 20, 7, 1, 9, 15, 4, 6]
LEAD = ([1, 2, 3], [0.125, 0.75, 0.125])


def run(seed, s=30, q=60, weeks=2000):
    return simulate(BOOT, s, q, LEAD[0], LEAD[1], seed, weeks, 52)


def test_same_seed_gives_identical_output():
    assert run(7) == run(7)


def test_different_seed_stays_within_tolerance():
    """Two seeds over 2000 weeks (about 250 order cycles) agree on cycle service
    level within 0.10 and on fill rate within 0.05 (stated tolerances; the
    standard error of a service level from 250 cycles is about 0.03)."""
    a, b = run(1), run(2)
    assert abs(a["cycle_service_level"] - b["cycle_service_level"]) <= 0.10
    assert abs(a["fill_rate"] - b["fill_rate"]) <= 0.05


def test_kpis_hand_worked_no_shortage():
    """Constant demand 10, lead time 1 week, s=10, Q=50, start on hand 60.
    Orders fire when position hits 10 and arrive before stock runs out:
    every 5 weeks, no shortage -> fill 1.0, service 1.0, no stockout weeks."""
    out = simulate([10], 10, 50, [1], [1.0], 1, 60, 5)
    assert out["fill_rate"] == 1.0
    assert out["cycle_service_level"] == 1.0
    assert out["stockout_weeks_per_year"] == 0.0


def test_kpis_hand_worked():
    """Constant demand 10, lead time 1, s=5, Q=50, start on hand 55.
    Steady 6-week cycle, on hand at week ends 40,30,20,10,0,50 (sum 150):
    week 5 of the cycle is short by 10 of 60 demanded.
    fill = 50/60; service = 0 (each order meets a shortage);
    stockout weeks = 1 in 6 -> 52/6 per year; average inventory = 150/6 = 25;
    turns = 10*52/25 = 20.8. Window: 6 warm-up weeks then 60 weeks = 10 cycles."""
    out = simulate([10], 5, 50, [1], [1.0], 1, 60, 6)
    assert abs(out["fill_rate"] - 50 / 60) < 1e-12
    assert out["cycle_service_level"] == 0.0
    assert out["orders"] == 10
    assert abs(out["stockout_weeks_per_year"] - 52 / 6) < 1e-9
    assert abs(out["avg_inventory"] - 25.0) < 1e-9
    assert abs(out["turns"] - 20.8) < 1e-9
