"""Swing points (HH/HL/LH/LL) y Market Structure Shift (MSS) por cierre de vela.

Definición cerrada con Albert (sección 2 del brief): el MSS se confirma
únicamente por el CIERRE (cuerpo) de una vela de 5 minutos más allá del
último swing relevante — una mecha no basta. No se usan proxies adicionales
de fuerza del impulso (ATR/ADX/solape): la propia secuencia sweep → MSS por
cierre acota qué cuenta como impulso válido (ver docs/STRATEGY_SPEC.md).
"""

from __future__ import annotations

from .models import Candle, SwingKind, SwingPoint


def find_pivots(candles: list[Candle], left: int = 1, right: int = 1) -> list[SwingPoint]:
    """Fractales simples: un pivote de máximo/mínimo requiere `left` velas antes
    y `right` velas después con un extremo estrictamente menos favorable.
    """
    pivots: list[SwingPoint] = []
    n = len(candles)
    for i in range(left, n - right):
        window_high = candles[i].high
        window_low = candles[i].low

        is_high = all(candles[i - k].high < window_high for k in range(1, left + 1)) and all(
            candles[i + k].high < window_high for k in range(1, right + 1)
        )
        is_low = all(candles[i - k].low > window_low for k in range(1, left + 1)) and all(
            candles[i + k].low > window_low for k in range(1, right + 1)
        )

        if is_high:
            pivots.append(SwingPoint(index=i, timestamp=candles[i].timestamp, price=window_high, is_high=True))
        if is_low:
            pivots.append(SwingPoint(index=i, timestamp=candles[i].timestamp, price=window_low, is_high=False))

    return pivots


def classify_swings(pivots: list[SwingPoint]) -> list[SwingPoint]:
    """Etiqueta cada pivote como HH/HL (máximos) o LH/LL (mínimos) comparándolo
    con el pivote previo del mismo tipo (solo máximos entre sí, solo mínimos
    entre sí), en orden cronológico.
    """
    classified: list[SwingPoint] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None

    for p in sorted(pivots, key=lambda sp: sp.index):
        if p.is_high:
            kind = SwingKind.HH if last_high is None or p.price > last_high.price else SwingKind.LH
            classified.append(SwingPoint(p.index, p.timestamp, p.price, True, kind))
            last_high = p
        else:
            kind = SwingKind.HL if last_low is None or p.price > last_low.price else SwingKind.LL
            classified.append(SwingPoint(p.index, p.timestamp, p.price, False, kind))
            last_low = p

    return classified


def last_swing_before(swings: list[SwingPoint], kind: SwingKind, before_index: int) -> SwingPoint | None:
    candidates = [s for s in swings if s.kind == kind and s.index < before_index]
    return max(candidates, key=lambda s: s.index) if candidates else None


def detect_mss(
    candles: list[Candle],
    reference_level: float,
    is_short: bool,
    search_start_index: int,
    search_end_index: int | None = None,
) -> int | None:
    """Devuelve el índice de la primera vela cuyo CIERRE confirma el MSS.

    Short: cierre por debajo de `reference_level` (el último HL previo al sweep).
    Long: cierre por encima de `reference_level` (el último LH previo al sweep).
    Una mecha que perfore el nivel sin que el cuerpo cierre más allá NO cuenta.
    """
    end = search_end_index if search_end_index is not None else len(candles)
    for i in range(search_start_index, end):
        close = candles[i].close
        if is_short and close < reference_level:
            return i
        if not is_short and close > reference_level:
            return i
    return None
