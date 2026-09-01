"""Filtro de alineación con estructura de 15 minutos (Sección 3 del brief —
el hallazgo más robusto del estudio cuantitativo: +0.93R medio alineado vs
+0.17R en contra, p=0.001, replicado out-of-sample).

El filtro de 1H no replica y el de 4H no tiene efecto/cambia de signo — no
se implementan como filtros de entrada, solo como contexto informativo para
el dashboard (fuera del alcance de este módulo).

Política CONFIRMADA por Albert: descartar (`skip`) la operación cuando el
15m está en contra, en vez de reducir tamaño — es lo que se simuló en el
estudio (PF 2.67→4.04, DD máx 5.0R→4.0R, a cambio de -36% operaciones).
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
    mode: Literal["skip", "reduce"] = "skip"
    reduced_size_multiplier: float = 0.5  # solo aplica si mode == "reduce"


@dataclass(frozen=True)
class M15FilterResult:
    aligned: bool | None  # None si no se pudo determinar el sesgo de 15m
    take_trade: bool
    size_multiplier: float


def evaluate_m15_filter(direction: Direction, m15_bias: Direction | None, policy: M15FilterPolicy) -> M15FilterResult:
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
