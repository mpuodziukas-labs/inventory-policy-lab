from lab.forecast import (
    mae,
    moving_average,
    naive_forecast,
    rolling_origin,
    ses,
    wape,
)


def test_naive_forecast_is_last_value():
    assert naive_forecast([3, 9, 4]) == 4


def test_moving_average_hand_worked():
    """History [2, 4, 6, 8], window 2: mean(6, 8) = 7."""
    assert moving_average([2, 4, 6, 8], 2) == 7.0


def test_ses_hand_worked():
    """alpha=0.5, history [10, 20, 30], level starts at the first value:
    l1 = 10; l2 = 0.5*20 + 0.5*10 = 15; l3 = 0.5*30 + 0.5*15 = 22.5."""
    assert ses([10, 20, 30], 0.5) == 22.5


def test_mae_hand_worked():
    """Actuals [10, 20], forecasts [12, 15]: errors 2 and 5, MAE = 3.5."""
    assert mae([10, 20], [12, 15]) == 3.5


def test_wape_hand_worked():
    """Actuals [10, 20], forecasts [12, 15]: sum|e| = 7, sum actual = 30,
    WAPE = 7/30 = 0.2333."""
    assert abs(wape([10, 20], [12, 15]) - 7 / 30) < 1e-12


def test_wape_defined_when_actuals_contain_zero():
    assert wape([0, 10], [2, 8]) == 4 / 10


def test_rolling_origin_has_no_lookahead():
    """Changing only the final observation must not change any earlier
    forecast: the forecast for week t uses weeks before t."""
    a = [5, 7, 6, 8, 9, 4, 10, 12]
    b = a[:-1] + [999]
    fa, ya = rolling_origin(a, naive_forecast, 3)
    fb, yb = rolling_origin(b, naive_forecast, 3)
    assert fa == fb
    assert ya[:-1] == yb[:-1] and ya[-1] != yb[-1]
    assert len(fa) == len(a) - 3
    assert fa[0] == a[2]
