"""Guardrails de riesgo (Sección 5 del brief) — ver docs/RISK_GUARDRAILS.md.

Estas clases están pensadas para ser imposibles de saltar por accidente: el
sizing siempre pasa por `position_size`, el límite diario es una máquina de
estados consultada antes de emitir cualquier señal, y el kill-switch de
drawdown expone un estado explícito (`ACTIVE` / `WARNING` / `HALTED`) en vez
de un booleano que se pueda ignorar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class InstrumentSpec:
    point_value: float = 1.0  # PLACEHOLDER — pregunta abierta #2, confirmar con el bróker real
    risk_per_trade_pct: float = 0.01
    max_stop_points: float = 75.0  # calibrado contra Full_Backtest.numbers, ver dax_model/entry.py


def position_size(equity: float, stop_distance_points: float, spec: InstrumentSpec = InstrumentSpec()) -> float:
    if stop_distance_points <= 0:
        raise ValueError("stop_distance_points must be > 0")
    if stop_distance_points > spec.max_stop_points:
        raise ValueError(
            f"stop_distance_points ({stop_distance_points}) excede max_stop_points "
            f"({spec.max_stop_points}) — esta operación debería haber sido descartada "
            f"por dax_model.entry.choose_entry antes de llegar aquí"
        )
    risk_amount = equity * spec.risk_per_trade_pct
    return risk_amount / (stop_distance_points * spec.point_value)


@dataclass
class DailyLimiter:
    """Máquina de estados para el máximo de 2 operaciones/día y el corte
    tras la primera pérdida. Reset explícito por día natural (CET) — el
    llamador es responsable de invocar `reset_if_new_day` con la fecha CET
    de la vela/evento actual antes de consultar `can_trade`.
    """

    max_trades_per_day: int = 2
    current_day: date | None = None
    trades_today: int = 0
    stopped_for_day: bool = False

    def reset_if_new_day(self, today: date) -> None:
        if self.current_day != today:
            self.current_day = today
            self.trades_today = 0
            self.stopped_for_day = False

    def can_trade(self) -> bool:
        return not self.stopped_for_day and self.trades_today < self.max_trades_per_day

    def record_trade_result(self, r_multiple: float) -> None:
        self.trades_today += 1
        if r_multiple < 0:
            self.stopped_for_day = True


class DrawdownState(Enum):
    ACTIVE = "active"
    WARNING = "warning"  # >= warning_threshold_pct del límite: no abrir operaciones nuevas
    HALTED = "halted"  # >= 100% del límite: cerrar posiciones + desactivar hasta reactivación manual


@dataclass(frozen=True)
class DrawdownLimits:
    daily_limit_pct: float = 0.05  # PLACEHOLDER — pregunta abierta #3
    total_limit_pct: float = 0.10  # PLACEHOLDER — pregunta abierta #3
    warning_threshold_pct: float = 0.80  # del propio límite (80%), no del equity


@dataclass
class DrawdownGuardrail:
    limits: DrawdownLimits = field(default_factory=DrawdownLimits)
    day_start_equity: float | None = None
    account_start_equity: float | None = None

    def start_new_day(self, equity: float) -> None:
        self.day_start_equity = equity
        if self.account_start_equity is None:
            self.account_start_equity = equity

    def evaluate(self, current_equity: float) -> DrawdownState:
        if self.day_start_equity is None or self.account_start_equity is None:
            raise ValueError("start_new_day must be called before evaluate")

        daily_dd = max(0.0, (self.day_start_equity - current_equity) / self.day_start_equity)
        total_dd = max(0.0, (self.account_start_equity - current_equity) / self.account_start_equity)

        daily_ratio = daily_dd / self.limits.daily_limit_pct
        total_ratio = total_dd / self.limits.total_limit_pct
        worst_ratio = max(daily_ratio, total_ratio)

        if worst_ratio >= 1.0:
            return DrawdownState.HALTED
        if worst_ratio >= self.limits.warning_threshold_pct:
            return DrawdownState.WARNING
        return DrawdownState.ACTIVE
