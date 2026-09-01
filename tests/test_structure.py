from __future__ import annotations

from helpers import candle, dt

from dax_model.models import SwingKind
from dax_model.structure import classify_swings, detect_mss, find_pivots, last_swing_before


def _sample_candles():
    # low pivot at index2 (89), high pivot at index3 (97), higher-low pivot at index4 (91)
    return [
        candle(dt(17, 23, 0), 95, 100, 95, 98),
        candle(dt(17, 23, 5), 95, 97, 90, 92),
        candle(dt(18, 7, 0), 90, 93, 89, 91),
        candle(dt(18, 7, 5), 94, 97, 93, 95),
        candle(dt(18, 7, 10), 92, 95, 91, 93),
        candle(dt(18, 7, 15), 94, 96, 94, 95),
    ]


def test_find_pivots_and_classify():
    candles = _sample_candles()
    pivots = find_pivots(candles, left=1, right=1)
    classified = classify_swings(pivots)

    lows = [p for p in classified if not p.is_high]
    assert any(p.index == 2 and p.price == 89 for p in lows)
    assert any(p.index == 4 and p.price == 91 for p in lows)

    # el primer low pivot es HL por convención (no hay low previo con el que compararlo)
    first_low = next(p for p in lows if p.index == 2)
    assert first_low.kind == SwingKind.HL

    # el segundo low pivot (91) es más alto que el primero (89) -> también HL
    second_low = next(p for p in lows if p.index == 4)
    assert second_low.kind == SwingKind.HL


def test_last_swing_before_picks_most_recent():
    candles = _sample_candles()
    classified = classify_swings(find_pivots(candles, left=1, right=1))
    ref = last_swing_before(classified, SwingKind.HL, before_index=6)
    assert ref is not None
    assert ref.index == 4
    assert ref.price == 91


def test_mss_requires_close_not_wick():
    # Vela con mecha por debajo del nivel pero cierre por encima -> NO confirma MSS
    candles = [
        candle(dt(18, 8, 20), 95, 96, 88, 93),  # wick to 88, close 93 (> 91)
        candle(dt(18, 8, 25), 93, 93, 80, 82),  # close 82 (< 91) -> confirma
    ]
    idx = detect_mss(candles, reference_level=91, is_short=True, search_start_index=0)
    assert idx == 1
