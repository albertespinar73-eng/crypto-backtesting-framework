"""Regla de breakeven (Sección 2 del brief; ver también Sección 3 y la
pregunta abierta #7 de docs/OPEN_QUESTIONS.md).

Se implementa la regla BASE del PDF tal cual, como parámetro configurable —
no una "regla mejorada", porque el estudio de BE (`be_rule_study`) todavía
está pendiente de datos completos (n=12 de 37 operaciones BE decididas).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Candle, Direction
from .structure import detect_mss


@dataclass(frozen=True)
class BreakevenPolicy:
    min_r_multiple: float = 1.0


def check_breakeven(
    candles: list[Candle],
    direction: Direction,
    entry_price: float,
    stop_loss: float,
    reference_level: float,
    current_index: int,
    search_start_index: int,
    policy: BreakevenPolicy = BreakevenPolicy(),
) -> bool:
    """True si, a fecha de `current_index`, el trade cumple las dos
    condiciones de la regla base:
      1. El precio de cierre actual implica un R multiple > `min_r_multiple`.
      2. Hay un BoS de 5m confirmado por cierre más allá de `reference_level`
         (el último high/low relevante) en algún punto entre
         `search_start_index` y `current_index`.

    No se mueve a BE de forma anticipada sin ambas condiciones.
    """
    risk_points = abs(entry_price - stop_loss)
    if risk_points == 0:
        return False

    current_close = candles[current_index].close
    is_short = direction == Direction.SHORT
    move_points = (entry_price - current_close) if is_short else (current_close - entry_price)
    r_multiple = move_points / risk_points

    if r_multiple <= policy.min_r_multiple:
        return False

    bos_index = detect_mss(
        candles,
        reference_level=reference_level,
        is_short=is_short,
        search_start_index=search_start_index,
        search_end_index=current_index + 1,
    )
    return bos_index is not None
