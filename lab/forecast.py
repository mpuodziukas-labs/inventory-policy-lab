"""Forecast methods, rolling-origin backtest and error measures."""


def naive_forecast(history):
    return history[-1]


def moving_average(history, k):
    window = history[-k:]
    return sum(window) / len(window)


def ses(history, alpha):
    level = history[0]
    for y in history[1:]:
        level = alpha * y + (1 - alpha) * level
    return level


def rolling_origin(series, method, min_train):
    """One-step-ahead forecasts for every week from min_train on; the forecast
    for week t sees only weeks before t. Returns (forecasts, actuals)."""
    forecasts, actuals = [], []
    for t in range(min_train, len(series)):
        forecasts.append(method(series[:t]))
        actuals.append(series[t])
    return forecasts, actuals


def mae(actuals, forecasts):
    return sum(abs(a - f) for a, f in zip(actuals, forecasts)) / len(actuals)


def wape(actuals, forecasts):
    """Sum of absolute errors over sum of actuals (defined when some weeks are zero)."""
    return sum(abs(a - f) for a, f in zip(actuals, forecasts)) / sum(actuals)
