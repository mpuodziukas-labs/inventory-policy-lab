"""Seeded (s, Q) continuous-review simulation with bootstrap demand and variable lead time.

Weekly steps. Each week: demand is drawn from the SKU's own history and served
from stock (unmet demand is lost), orders due this week arrive, then orders of
size Q are placed while inventory position (on hand + on order) is at or below
s. An order placed at the end of week t arrives at the end of week t + L, so
its lead-time window is weeks t+1 .. t+L.
"""
import random


def _draw(rng, values, probs):
    u = rng.random()
    acc = 0.0
    for v, p in zip(values, probs):
        acc += p
        if u < acc:
            return v
    return values[-1]


def simulate(history, reorder_point, order_qty, lead_values, lead_probs, seed, weeks, warmup):
    if weeks <= 0:
        raise ValueError("weeks must be positive")
    rng = random.Random(seed)
    n = len(history)
    total = warmup + weeks
    on_hand = reorder_point + order_qty
    on_order = 0
    arrivals = {}
    short_week = [False] * (total + 2)
    orders = []
    demanded = short_units = inv_sum = 0.0
    for t in range(1, total + 1):
        d = history[int(rng.random() * n)]
        sold = min(on_hand, d)
        on_hand -= sold
        if t in arrivals:
            on_hand += arrivals[t]
            on_order -= arrivals[t]
        short_week[t] = d > sold
        if t > warmup:
            demanded += d
            short_units += d - sold
            inv_sum += on_hand
        while on_hand + on_order <= reorder_point:
            lead = _draw(rng, lead_values, lead_probs)
            arrivals[t + lead] = arrivals.get(t + lead, 0) + order_qty
            on_order += order_qty
            if t > warmup:
                orders.append((t, lead))
    done = [(t, lead) for t, lead in orders if t + lead <= total]
    if not done:
        raise ValueError("no completed order cycles; lengthen the simulation")
    served = sum(1 for t, lead in done if not any(short_week[t + 1:t + lead + 1]))
    avg_inv = inv_sum / weeks
    mean_demand = demanded / weeks
    stock_weeks = sum(1 for t in range(warmup + 1, total + 1) if short_week[t])
    return {
        "cycle_service_level": served / len(done),
        "fill_rate": 1 - short_units / demanded if demanded else 1.0,
        "stockout_weeks_per_year": stock_weeks / weeks * 52,
        "avg_inventory": avg_inv,
        "turns": mean_demand * 52 / avg_inv if avg_inv else 0.0,
        "orders": len(done),
    }
