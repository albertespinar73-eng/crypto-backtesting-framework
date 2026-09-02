"""Filtro de alineación con estructura HTF (Sección 3 del brief).

Las funciones de este módulo son agnósticas al timeframe: se aplican tanto
al filtro de 15 minutos como al de 1 hora, pasando la serie de velas
correspondiente. El 4H nunca se usa como filtro (ver más abajo).

IMPORTANTE — los dos documentos de validación cuantitativa que Albert ha
subido NO están de acuerdo sobre el 1H, y esto se deja documentado en vez de
resuelto unilateralmente (ver docs/OPEN_QUESTIONS.md #11):

- `DAX40_Quantitative_Validation.pdf` (18-ago-2026, con bootstrap + split
  in/out-of-sample por fecha): el 15m es "the only conditional finding...
  that survives out-of-sample testing"; el 1H "loses two thirds of its size
  on unseen data" — no lo recomienda como filtro.
- `DAX40_Statistical_Review.pdf`: encuentra el 1H también significativo y
  robusto (p=0.0038) junto al 15m (p=0.0002), y construye un framework de
  tiers (A/A++) que usa AMBOS.

Por eso el filtro de 15m sigue activo por defecto (`enabled=True`, con la
política "skip" que Albert confirmó) y el de 1H se añade ahora pero
DESACTIVADO por defecto (`enabled=False`) — disponible para que Albert lo
active y compare con/sin en backtest, en vez de que el código decida por él
cuál de los dos informes seguir. El 4H no se implementa como filtro en
ningún caso: ambos documentos coinciden en que no aporta señal (Quant.
Validation no lo menciona como predictor; Statistical Review lo prueba
explícitamente y confirma p=0.396, no significativo, y que diluye la señal
cuando sustituye a 15m/1H).

Cada política tiene un `enabled: bool` para poder desactivar el filtro por
completo en un backtest (petición explícita de Albert: "que se pueda quitar
para hacer backtest con y sin", igual que el filtro de MA100 — ver
dax_model/trend_filter.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import Candle, Direction
from .structure import classify_swings, find_pivots


def compute_m15_bias(candles: list[Candle], left: int = 1, right: int = 1) -> Direction | None:
    """Sesgo de 15 minutos basado en la última ruptura de estructura
    confirmada por cierre (mismo criterio de cierre-de-vela que el MSS de
    5m, aplicado aquí a nivel de estructura general en vez de a un sweep
    concreto). Sin look-ahead: un pivote solo se usa una vez que sus
    `right` velas de confirmación ya han cerrado.
    """
    pivots = classify_swings(find_pivots(candles, left, right))
    pivots_by_confirmation = sorted(pivots, key=lambda p: p.index + right)

    bias: Direction | None = None
    last_high = None
    last_low = None
    pivot_ptr = 0

    for i, c in enumerate(candles):
        while pivot_ptr < len(pivots_by_confirmation) and pivots_by_confirmation[pivot_ptr].index + right <= i:
            p = pivots_by_confirmation[pivot_ptr]
            if p.is_high:
                last_high = p
            else:
                last_low = p
            pivot_ptr += 1

        if last_high is not None and c.close > last_high.price:
            bias = Direction.LONG
        if last_low is not None and c.close < last_low.price:
            bias = Direction.SHORT

    return bias


@dataclass(frozen=True)
class M15FilterPolicy:
    enabled: bool = True  # apagar para backtestear "sin filtro de estructura"
    mode: Literal["skip", "reduce"] = "skip"
    reduced_size_multiplier: float = 0.5  # solo aplica si mode == "reduce"


@dataclass(frozen=True)
class M15FilterResult:
    aligned: bool | None  # None si el filtro está apagado o no se pudo determinar el sesgo
    take_trade: bool
    size_multiplier: float


def evaluate_m15_filter(direction: Direction, m15_bias: Direction | None, policy: M15FilterPolicy) -> M15FilterResult:
    if not policy.enabled:
        return M15FilterResult(aligned=None, take_trade=True, size_multiplier=1.0)

    if m15_bias is None:
        # Sin datos suficientes de 15m: no se puede confirmar alineación.
        # Se trata como "en contra" por prudencia (nunca se asume alineado sin evidencia).
        aligned = False
    else:
        aligned = m15_bias == direction

    if aligned:
        return M15FilterResult(aligned=aligned, take_trade=True, size_multiplier=1.0)

    if policy.mode == "skip":
        return M15FilterResult(aligned=aligned, take_trade=False, size_multiplier=0.0)

    return M15FilterResult(aligned=aligned, take_trade=True, size_multiplier=policy.reduced_size_multiplier)
