from __future__ import annotations

from helpers import candle, dt

from dax_model.fvg import find_fvgs, is_mitigated
from dax_model.models import FvgType


def test_find_fvgs_bearish():
    candles = [
        candle(dt(18, 8, 20), 95, 102, 95, 97),  # candle1: low=95
        candle(dt(18, 8, 25), 97, 98, 92, 93),  # candle2
        candle(dt(18, 8, 30), 93, 93, 80, 82),  # candle3: high=93 < candle1.low=95
    ]
    fvgs = find_fvgs(candles, 0, 3)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.fvg_type == FvgType.BEARISH
    assert fvg.top == 95
    assert fvg.bottom == 93


def test_find_fvgs_bullish():
    candles = [
        candle(dt(18, 8, 20), 90, 92, 88, 91),  # candle1: high=92
        candle(dt(18, 8, 25), 91, 96, 91, 95),  # candle2
        candle(dt(18, 8, 30), 96, 100, 95, 99),  # candle3: low=95 > candle1.high=92
    ]
    fvgs = find_fvgs(candles, 0, 3)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.fvg_type == FvgType.BULLISH
    assert fvg.bottom == 92
    assert fvg.top == 95


def test_no_fvg_when_candles_overlap():
    candles = [
        candle(dt(18, 8, 20), 95, 98, 92, 96),
        candle(dt(18, 8, 25), 96, 97, 93, 94),
        candle(dt(18, 8, 30), 94, 97, 91, 95),  # overlaps candle1's range -> no gap
    ]
    assert find_fvgs(candles, 0, 3) == []


def test_is_mitigated_full_fill():
    candles = [
        candle(dt(18, 8, 20), 95, 102, 95, 97),
        candle(dt(18, 8, 25), 97, 98, 92, 93),
        candle(dt(18, 8, 30), 93, 93, 80, 82),
        candle(dt(18, 8, 35), 82, 96, 82, 95),  # trades back through the whole [93,95] gap
    ]
    fvg = find_fvgs(candles, 0, 3)[0]
    assert is_mitigated(fvg, candles, up_to_index=4) is True
    assert is_mitigated(fvg, candles, up_to_index=3) is False
