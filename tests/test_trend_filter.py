from __future__ import annotations

from helpers import candle, dt

from dax_model.models import Direction
from dax_model.trend_filter import (
    MATrendFilterPolicy,
    compute_ma_trend_bias,
    evaluate_ma_trend_filter,
    simple_moving_average,
)


def _flat_candles(n: int, close: float) -> list:
    return [candle(dt(1, 0, i % 60, month=1), close, close, close, close) for i in range(n)]


def test_simple_moving_average_needs_full_window():
    candles = _flat_candles(5, 100)
    assert simple_moving_average(candles, period=10, up_to_index=4) is None
    assert simple_moving_average(candles, period=5, up_to_index=4) == 100


def test_compute_ma_trend_bias_long_and_short():
    # 99 velas planas en 100, última vela sube muy por encima -> close > SMA100 -> LONG
    candles = _flat_candles(99, 100)
    candles.append(candle(dt(5, 0, 0, month=1), 100, 150, 100, 150))
    assert compute_ma_trend_bias(candles, period=100) == Direction.LONG

    candles2 = _flat_candles(99, 100)
    candles2.append(candle(dt(5, 0, 0, month=1), 100, 100, 50, 50))
    assert compute_ma_trend_bias(candles2, period=100) == Direction.SHORT


def test_compute_ma_trend_bias_none_when_insufficient_data():
    candles = _flat_candles(10, 100)
    assert compute_ma_trend_bias(candles, period=100) is None


def test_evaluate_ma_trend_filter_disabled_always_takes_trade():
    policy = MATrendFilterPolicy(enabled=False)
    result = evaluate_ma_trend_filter(Direction.LONG, Direction.SHORT, policy)
    assert result.take_trade is True
    assert result.aligned is None


def test_evaluate_ma_trend_filter_enabled_blocks_misaligned():
    policy = MATrendFilterPolicy(enabled=True)
    result = evaluate_ma_trend_filter(Direction.LONG, Direction.SHORT, policy)
    assert result.take_trade is False
    assert result.aligned is False


def test_evaluate_ma_trend_filter_enabled_allows_aligned():
    policy = MATrendFilterPolicy(enabled=True)
    result = evaluate_ma_trend_filter(Direction.LONG, Direction.LONG, policy)
    assert result.take_trade is True
    assert result.aligned is True


def test_evaluate_ma_trend_filter_no_bias_is_treated_as_misaligned():
    policy = MATrendFilterPolicy(enabled=True)
    result = evaluate_ma_trend_filter(Direction.LONG, None, policy)
    assert result.take_trade is False
