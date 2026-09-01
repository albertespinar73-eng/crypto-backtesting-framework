"""Fair Value Gaps (FVG) de 3 velas y su mitigación.

Un FVG bajista (bearish) se forma cuando la vela 1 y la vela 3 de un tramo
impulsivo bajista no solapan: `candle1.low > candle3.high`. El hueco
resultante es `[candle3.high, candle1.low]`. Simétrico para el alcista.
"""

from __future__ import annotations

from .models import Candle, FVG, FvgType


def find_fvgs(candles: list[Candle], start_index: int, end_index: int) -> list[FVG]:
    """Busca FVGs de 3 velas dentro de `candles[start_index:end_index]` (el
    tramo de displacement, según docs/STRATEGY_SPEC.md), devueltos en orden
    cronológico (primero = más cercano al sweep, no al origen).
    """
    fvgs: list[FVG] = []
    for i in range(start_index, end_index - 2):
        c1, c3 = candles[i], candles[i + 2]

        if c1.low > c3.high:
            fvgs.append(
                FVG(
                    fvg_type=FvgType.BEARISH,
                    candle1_index=i,
                    candle2_index=i + 1,
                    candle3_index=i + 2,
                    top=c1.low,
                    bottom=c3.high,
                    formed_at=candles[i + 2].timestamp,
                )
            )
        elif c1.high < c3.low:
            fvgs.append(
                FVG(
                    fvg_type=FvgType.BULLISH,
                    candle1_index=i,
                    candle2_index=i + 1,
                    candle3_index=i + 2,
                    top=c3.low,
                    bottom=c1.high,
                    formed_at=candles[i + 2].timestamp,
                )
            )

    return fvgs


def is_mitigated(fvg: FVG, candles: list[Candle], up_to_index: int, full_fill: bool = True) -> bool:
    """Comprueba si el FVG ya fue rellenado por precio antes de `up_to_index`
    (exclusivo). `full_fill=True` exige que el precio haya atravesado todo el
    hueco (borde a borde); `full_fill=False` basta con tocarlo.
    """
    start = fvg.candle3_index + 1
    for i in range(start, min(up_to_index, len(candles))):
        c = candles[i]
        if full_fill:
            if c.low <= fvg.bottom and c.high >= fvg.top:
                return True
        else:
            if c.high >= fvg.bottom and c.low <= fvg.top:
                return True
    return False
