"""Rango asiático y ventana de killzone (Sección 2 del brief).

La hora de apertura de la sesión nocturna del DAX40 CFD depende del bróker
(pregunta abierta #1 en docs/OPEN_QUESTIONS.md) — aquí se deja como
parámetro configurable con un placeholder, nunca hardcodeada sin forma de
cambiarla.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from .models import Candle


@dataclass(frozen=True)
class AsianSessionConfig:
    open_time_cet: time = time(23, 0)  # PLACEHOLDER — pregunta abierta #1
    close_time_cet: time = time(6, 0)  # fijado por Albert, no es una pregunta abierta


@dataclass(frozen=True)
class KillzoneConfig:
    start_cet: time = time(8, 15)
    end_cet: time = time(10, 45)


@dataclass(frozen=True)
class AsianRange:
    high: float
    low: float
    equilibrium: float
    start_index: int
    end_index: int

    @classmethod
    def from_candles(cls, candles: list[Candle], start_index: int, end_index: int) -> "AsianRange":
        window = candles[start_index:end_index]
        if not window:
            raise ValueError("Asian range window is empty — check session config against the candle series")
        high = max(c.high for c in window)
        low = min(c.low for c in window)
        return cls(
            high=high,
            low=low,
            equilibrium=(high + low) / 2,
            start_index=start_index,
            end_index=end_index,
        )


def _in_window(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # ventana que cruza medianoche


def compute_asian_range(candles: list[Candle], config: AsianSessionConfig = AsianSessionConfig()) -> AsianRange:
    """Calcula el rango asiático a partir de una serie de velas ya filtrada al día en curso.

    Asume que `candles` contiene, como mínimo, todas las velas entre la
    apertura nocturna y las 06:00 CET del día que se quiere medir. La
    responsabilidad de recortar la serie por fecha vive en el llamador
    (backtest_loader / futura ingesta en vivo).
    """
    indices = [i for i, c in enumerate(candles) if _in_window(c.timestamp.timetz().replace(tzinfo=None), config.open_time_cet, config.close_time_cet)]
    if not indices:
        raise ValueError("No candles found inside the Asian session window")
    return AsianRange.from_candles(candles, indices[0], indices[-1] + 1)


def is_in_killzone(ts: datetime, config: KillzoneConfig = KillzoneConfig()) -> bool:
    t = ts.timetz().replace(tzinfo=None)
    return config.start_cet <= t <= config.end_cet
