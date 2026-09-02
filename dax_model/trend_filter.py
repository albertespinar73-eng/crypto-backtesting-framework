"""Filtro de tendencia por media móvil simple de 100 periodos (SMA100).

Feature NUEVA pedida por Albert — NO validada por ninguno de los tres
documentos cuantitativos subidos (`DAX40_Quantitative_Validation.pdf`,
`DAX40_Statistical_Review.pdf`, `Asian_Sweep_Paper.pdf`): ninguno prueba ni
menciona un filtro de media móvil. Se implementa **apagada por defecto**
(`enabled=False`) y completamente independiente del resto del motor, para
poder compararla con/sin en backtest antes de decidir si aporta algo — tal
como se pidió explícitamente, igual que el toggle del filtro de estructura
en `dax_model/htf_filter.py`.

Regla simple y estándar (no hay nada más específico que calibrar todavía,
porque no hay datos sobre esto): tendencia LONG si el último cierre está
por encima de la SMA(period) en el timeframe elegido, SHORT si está por
debajo. Sin pendiente/inclinación de la media ni bandas — si Albert quiere
una variante más elaborada, es una siguiente iteración informada por lo que
salga del backtest con/sin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import Candle, Direction


def simple_moving_average(candles: list[Candle], period: int, up_to_index: int) -> float | None:
    """Media de los `period` cierres que terminan en `up_to_index` (inclusive).
    None si no hay suficientes velas todavía.
    """
    if up_to_index - period + 1 < 0:
        return None
    window = candles[up_to_index - period + 1 : up_to_index + 1]
    return sum(c.close for c in window) / period


def compute_ma_trend_bias(candles: list[Candle], period: int = 100) -> Direction | None:
    """Sesgo de tendencia a partir de la última vela de `candles` frente a
    la SMA(period) calculada hasta ese mismo punto (sin look-ahead: solo usa
    velas ya cerradas dentro de `candles`)."""
    if not candles:
        return None
    ma_value = simple_moving_average(candles, period, len(candles) - 1)
    if ma_value is None:
        return None
    last_close = candles[-1].close
    if last_close > ma_value:
        return Direction.LONG
    if last_close < ma_value:
        return Direction.SHORT
    return None  # exactamente sobre la media: sin sesgo


@dataclass(frozen=True)
class MATrendFilterPolicy:
    enabled: bool = False  # apagado por defecto — feature sin validar todavía
    period: int = 100
    timeframe: Literal["15m", "1h"] = "1h"


@dataclass(frozen=True)
class MATrendFilterResult:
    aligned: bool | None  # None si el filtro está apagado o no hay suficientes velas
    take_trade: bool


def evaluate_ma_trend_filter(
    direction: Direction, trend_bias: Direction | None, policy: MATrendFilterPolicy
) -> MATrendFilterResult:
    if not policy.enabled:
        return MATrendFilterResult(aligned=None, take_trade=True)

    if trend_bias is None:
        # No hay suficientes velas para calcular la SMA todavía: no se
        # puede confirmar alineación, se trata como "en contra" por
        # prudencia (mismo criterio que el filtro de estructura).
        return MATrendFilterResult(aligned=False, take_trade=False)

    aligned = trend_bias == direction
    return MATrendFilterResult(aligned=aligned, take_trade=aligned)
