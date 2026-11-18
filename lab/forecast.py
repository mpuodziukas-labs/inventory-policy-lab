"""Forecast methods, rolling-origin backtest and error measures."""
import math


def _require_series(history):
    if len(history) == 0:
        raise ValueError("series must not be empty")


def naive_forecast(history):
    _require_series(history)
    return history[-1]


def moving_average(history, k):
    if k < 1:
        raise ValueError("moving average window must be at least 1")
    _require_series(history)
    window = history[-k:]
    return sum(window) / len(window)


def ses(history, alpha):
    if not 0 < alpha <= 1:  # also rejects NaN, which fails every comparison
        raise ValueError("ses alpha must be above 0 and at most 1")
    _require_series(history)
    level = history[0]
    for y in history[1:]:
        level = alpha * y + (1 - alpha) * level
    return level


def rolling_origin(series, method, min_train):
    """One-step-ahead forecasts for every week from min_train on; the forecast
    for week t sees only weeks before t. Returns (forecasts, actuals)."""
    if min_train < 1:
        raise ValueError("min_train must be at least 1")
    forecasts, actuals = [], []
    for t in range(min_train, len(series)):
        forecasts.append(method(series[:t]))
        actuals.append(series[t])
    return forecasts, actuals


def _require_finite(name, actuals, forecasts):
    if not all(math.isfinite(v) for v in (*actuals, *forecasts)):
        raise ValueError(f"{name} is undefined: actuals and forecasts must be finite numbers")


def mae(actuals, forecasts):
    if not actuals:
        raise ValueError("MAE is undefined: no test weeks (the series is no longer than the training minimum)")
    if len(actuals) != len(forecasts):
        raise ValueError(f"MAE is undefined: {len(actuals)} actuals but {len(forecasts)} forecasts (length mismatch)")
    _require_finite("MAE", actuals, forecasts)
    return sum(abs(a - f) for a, f in zip(actuals, forecasts)) / len(actuals)


def wape(actuals, forecasts):
    """Sum of absolute errors over sum of actuals (defined when some weeks are zero, undefined when all are)."""
    if len(actuals) != len(forecasts):
        raise ValueError(f"WAPE is undefined: {len(actuals)} actuals but {len(forecasts)} forecasts (length mismatch)")
    _require_finite("WAPE", actuals, forecasts)
    if any(a < 0 for a in actuals):
        raise ValueError("WAPE is undefined: demand actuals cannot be negative")
    if sum(actuals) == 0:
        raise ValueError("WAPE is undefined: the actuals sum to zero")
    return sum(abs(a - f) for a, f in zip(actuals, forecasts)) / sum(actuals)
