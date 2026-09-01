from __future__ import annotations

from helpers import candle, dt

from dax_model.htf_filter import M15FilterPolicy, compute_m15_bias, evaluate_m15_filter
from dax_model.models import Direction


def test_compute_m15_bias_detects_bearish_break():
    candles = [
        candle(dt(18, 6, 45), 96, 100, 95, 98),
        candle(dt(18, 7, 0), 97, 98, 90, 93),  # pivot low candidate (90)
        candle(dt(18, 7, 15), 95, 99, 94, 96),  # confirms the pivot (low=94 > 90)
        candle(dt(18, 7, 30), 89, 97, 88, 89),  # close 89 < 90 -> bias SHORT
    ]
    assert compute_m15_bias(candles) == Direction.SHORT


def test_evaluate_m15_filter_skip_policy_discards_misaligned():
    result = evaluate_m15_filter(Direction.LONG, Direction.SHORT, M15FilterPolicy(mode="skip"))
    assert result.aligned is False
    assert result.take_trade is False


def test_evaluate_m15_filter_reduce_policy_keeps_trade_with_smaller_size():
    result = evaluate_m15_filter(Direction.LONG, Direction.SHORT, M15FilterPolicy(mode="reduce", reduced_size_multiplier=0.5))
    assert result.aligned is False
    assert result.take_trade is True
    assert result.size_multiplier == 0.5


def test_evaluate_m15_filter_unknown_bias_treated_as_not_aligned():
    result = evaluate_m15_filter(Direction.LONG, None, M15FilterPolicy(mode="skip"))
    assert result.take_trade is False
