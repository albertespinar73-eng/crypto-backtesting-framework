"""Lógica de prioridad de entrada/SL (Sección 2 del brief, ejemplo #6 del
Apéndice A).

Orden de prioridad: el FVG más cercano al precio actual (el que se toca
primero si el precio retrocede desde el extremo del impulso) se intenta
primero; si su borde más profundo hacia el origen ya excede `max_sl_points`,
se prueba el siguiente FVG (formado más cerca del origen, por tanto con
menor distancia potencial al SL). Si ninguno cabe, se descarta la operación.

La precisión exacta del punto de entrada dentro del FVG (el borde más
cercano al origen, frente a un nivel más fino como la apertura de la vela de
displacement más grande) es la pregunta abierta #4 de
docs/OPEN_QUESTIONS.md — aquí se implementa la interpretación mecánica más
simple consistente con el ejemplo SL≈60 del Apéndice A, expuesta como
`EntryPolicy` para poder ajustarla sin tocar la lógica de orquestación.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import FVG, Entry


@dataclass(frozen=True)
class EntryPolicy:
    max_sl_points: float = 70.0


def order_fvgs_by_priority(fvgs: list[FVG], origin: float) -> list[FVG]:
    """Del más cercano al precio actual (mayor distancia a `origin`) al más
    cercano al origen (menor distancia)."""
    return sorted(fvgs, key=lambda f: abs(origin - f.near_edge(origin)), reverse=True)


def choose_entry(fvgs: list[FVG], origin: float, policy: EntryPolicy = EntryPolicy()) -> Entry | None:
    """`fvgs` debe contener únicamente FVGs no mitigados del tramo de
    displacement en curso (ver fvg.is_mitigated) — la mitigación se filtra
    antes de llamar a esta función, no dentro de ella.
    """
    for rank, candidate in enumerate(order_fvgs_by_priority(fvgs, origin)):
        near = candidate.near_edge(origin)
        distance = abs(origin - near)
        if distance <= policy.max_sl_points:
            return Entry(
                price=near,
                stop_loss=origin,
                fvg=candidate,
                stop_distance_points=distance,
                fvg_rank=rank,
            )
    return None
