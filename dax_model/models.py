"""Estructuras de datos compartidas por todo el motor de detección.

Ninguna clase aquí depende de una fuente de datos concreta (MT5, CSV,
numbers-parser): todo opera sobre `Candle` en memoria para que la misma
lógica sirva para backtest offline y, más adelante, para datos en vivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(Enum):
    LONG = "long"
    SHORT = "short"


class SwingKind(Enum):
    HH = "higher_high"
    HL = "higher_low"
    LH = "lower_high"
    LL = "lower_low"


class SetupModel(Enum):
    PRIMARY_SWEEP = "primary_sweep"
    ALTERNATIVE_INTERNAL = "alternative_internal"
    CONTINUATION = "continuation"


class FvgType(Enum):
    BULLISH = "bullish"  # gap dejado por un impulso alcista (candle1.high < candle3.low)
    BEARISH = "bearish"  # gap dejado por un impulso bajista (candle1.low > candle3.high)


@dataclass(frozen=True)
class Candle:
    timestamp: datetime  # timezone-aware, se recomienda Europe/Berlin (CET/CEST)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    is_high: bool  # True = pivot de máximo, False = pivot de mínimo
    kind: SwingKind | None = None  # se rellena tras clasificar contra el pivot previo del mismo tipo


@dataclass(frozen=True)
class FVG:
    fvg_type: FvgType
    candle1_index: int
    candle2_index: int
    candle3_index: int
    top: float  # borde superior del hueco
    bottom: float  # borde inferior del hueco
    formed_at: datetime

    def near_edge(self, origin: float) -> float:
        """Borde del FVG más cercano a `origin` (el punto más profundo alcanzable)."""
        return self.top if abs(origin - self.top) <= abs(origin - self.bottom) else self.bottom

    def far_edge(self, origin: float) -> float:
        return self.bottom if self.near_edge(origin) == self.top else self.top

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass(frozen=True)
class Entry:
    price: float
    stop_loss: float
    fvg: FVG
    stop_distance_points: float
    fvg_rank: int  # 0 = primer FVG del tramo, 1 = siguiente, ...


@dataclass(frozen=True)
class DiscardReason:
    code: str
    detail: str


@dataclass
class Setup:
    model: SetupModel
    direction: Direction
    sweep_index: int
    sweep_price: float
    mss_index: int
    mss_close: float
    entry: Entry
    take_profit: float
    m15_aligned: bool | None  # None si el filtro está apagado o no se pudo evaluar
    h1_aligned: bool | None = None  # None si el filtro está apagado (por defecto) o no se pudo evaluar
    ma_trend_aligned: bool | None = None  # None si el filtro está apagado (por defecto) o no se pudo evaluar


@dataclass
class DiscardedSetup:
    model: SetupModel
    direction: Direction
    sweep_index: int
    reason: DiscardReason
