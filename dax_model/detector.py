"""Orquestador del Modelo Primario (Asian Liquidity Sweep) — Sección 2.

Combina sessions/structure/fvg/entry/htf_filter sobre una serie de velas de
5m (más una serie de 15m para el filtro de alineación) y produce, para una
sesión dada, la lista de `Setup` tomables y `DiscardedSetup` con motivo.

Alcance de esta primera versión (Fase 0):

- Implementa completo el **Modelo primario** (barrido de Asian High/Low).
- El **Modelo alternativo** (liquidez interna) y el **Modelo de
  continuación** (segundo BoS) reutilizan exactamente los mismos primitivos
  (`find_pivots`, `detect_mss`, `find_fvgs`, `choose_entry`) — lo único que
  cambia es qué swing se usa como nivel de liquidez de partida. No se han
  implementado todavía porque requieren calibrar contra `Full
  Backtest.numbers` qué cuenta como "liquidez interna" de forma objetiva
  (ver docs/OPEN_QUESTIONS.md) — se ha preferido no inventar un umbral no
  pedido por Albert antes de tener esos datos.
- La mitigación de FVGs se evalúa en un único punto (el instante en que el
  MSS confirma, o el inicio de la killzone si el MSS ya se confirmó antes) —
  no una simulación vela a vela de cuándo exactamente se rellena cada hueco.
  Es una simplificación documentada, a refinar en cuanto haya datos reales
  con los que comparar fills.
- El take-profit implementado es únicamente RR 1:2 fijo. La extensión de
  objetivo hacia PDH/PDL/liquidez de HTF (Sección 2) no está implementada
  todavía — requiere una serie multi-día y no está especificada con
  precisión suficiente para mecanizarla sin más ejemplos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .entry import EntryPolicy, choose_entry
from .fvg import find_fvgs, is_mitigated
from .htf_filter import M15FilterPolicy, compute_m15_bias, evaluate_m15_filter
from .models import Candle, DiscardedSetup, DiscardReason, Direction, Entry, Setup, SetupModel
from .sessions import AsianRange, KillzoneConfig, is_in_killzone
from .structure import classify_swings, detect_mss, find_pivots, last_swing_before
from .models import SwingKind


@dataclass(frozen=True)
class DetectorConfig:
    killzone: KillzoneConfig = KillzoneConfig()
    entry_policy: EntryPolicy = EntryPolicy()
    m15_policy: M15FilterPolicy = M15FilterPolicy()
    pivot_left: int = 1
    pivot_right: int = 1
    take_profit_rr: float = 2.0
    # Pregunta abierta #5 — ver docs/OPEN_QUESTIONS.md
    allow_pre_killzone_setups: bool = True


def _index_at_or_before(candles: list[Candle], ts: datetime) -> int:
    idx = -1
    for i, c in enumerate(candles):
        if c.timestamp <= ts:
            idx = i
        else:
            break
    return idx


def _find_sweep_index(candles: list[Candle], start_index: int, level: float, is_high_sweep: bool) -> int | None:
    for i in range(start_index, len(candles)):
        if is_high_sweep and candles[i].high > level:
            return i
        if not is_high_sweep and candles[i].low < level:
            return i
    return None


def _evaluate_direction(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
    asian_range: AsianRange,
    monitor_start_index: int,
    direction: Direction,
    config: DetectorConfig,
) -> Setup | DiscardedSetup | None:
    is_short = direction == Direction.SHORT
    sweep_level = asian_range.high if is_short else asian_range.low

    sweep_index = _find_sweep_index(candles_5m, monitor_start_index, sweep_level, is_high_sweep=is_short)
    if sweep_index is None:
        return None  # no ha habido barrido todavía con los datos disponibles

    # Nivel de referencia estructural (último HL para short / último LH para
    # long), calculado SOLO con velas previas al sweep para evitar look-ahead.
    pivots_before_sweep = classify_swings(find_pivots(candles_5m[: sweep_index + 1], config.pivot_left, config.pivot_right))
    ref_kind = SwingKind.HL if is_short else SwingKind.LH
    reference_swing = last_swing_before(pivots_before_sweep, ref_kind, before_index=sweep_index)
    if reference_swing is None:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("NO_REFERENCE_SWING", "No se encontró un HL/LH previo al sweep para definir el MSS"),
        )

    mss_index = detect_mss(
        candles_5m,
        reference_level=reference_swing.price,
        is_short=is_short,
        search_start_index=sweep_index + 1,
    )
    if mss_index is None:
        return None  # todavía no ha confirmado MSS con los datos disponibles

    mss_ts = candles_5m[mss_index].timestamp
    mss_in_killzone = is_in_killzone(mss_ts, config.killzone)

    if not mss_in_killzone and not config.allow_pre_killzone_setups:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("OUTSIDE_KILLZONE", "MSS confirmado fuera de la killzone 08:15-10:45 CET"),
        )

    origin = candles_5m[sweep_index].high if is_short else candles_5m[sweep_index].low

    fvgs = find_fvgs(candles_5m, sweep_index, mss_index + 1)
    if not fvgs:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("NO_FVG", "No se formó ningún FVG durante el tramo de displacement"),
        )

    mitigation_check_index = mss_index + 1 if mss_in_killzone else _index_at_or_before(
        candles_5m, datetime.combine(mss_ts.date(), config.killzone.start_cet, tzinfo=mss_ts.tzinfo)
    )
    unmitigated = [f for f in fvgs if not is_mitigated(f, candles_5m, mitigation_check_index)]
    if not unmitigated:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("ALL_FVG_MITIGATED", "Todos los FVGs del tramo ya estaban mitigados antes de poder entrar"),
        )

    entry = choose_entry(unmitigated, origin, config.entry_policy)
    if entry is None:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason(
                "SL_EXCEEDS_MAX",
                f"Ningún FVG disponible permite un SL <= {config.entry_policy.max_sl_points} puntos",
            ),
        )

    risk_points = entry.stop_distance_points
    take_profit = entry.price - (risk_points * config.take_profit_rr) if is_short else entry.price + (risk_points * config.take_profit_rr)

    m15_window = candles_15m[: _index_at_or_before(candles_15m, mss_ts) + 1] if candles_15m else []
    m15_bias = compute_m15_bias(m15_window) if m15_window else None
    m15_result = evaluate_m15_filter(direction, m15_bias, config.m15_policy)

    if not m15_result.take_trade:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("M15_MISALIGNED", "Estructura de 15m en contra de la dirección del setup"),
        )

    return Setup(
        model=SetupModel.PRIMARY_SWEEP,
        direction=direction,
        sweep_index=sweep_index,
        sweep_price=sweep_level,
        mss_index=mss_index,
        mss_close=candles_5m[mss_index].close,
        entry=entry,
        take_profit=take_profit,
        m15_aligned=m15_result.aligned,
    )


def detect_primary_setups(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
    asian_range: AsianRange,
    monitor_start_index: int,
    config: DetectorConfig = DetectorConfig(),
) -> list[Setup | DiscardedSetup]:
    """Evalúa ambas direcciones (barrido de Asian High -> short, barrido de
    Asian Low -> long) para una sesión y devuelve lo que haya encontrado.
    `monitor_start_index` es el índice en `candles_5m` a partir del cual
    empieza a monitorizarse el sweep (recomendado: justo tras el cierre del
    rango asiático, ver sessions.compute_asian_range).
    """
    results: list[Setup | DiscardedSetup] = []
    for direction in (Direction.SHORT, Direction.LONG):
        outcome = _evaluate_direction(candles_5m, candles_15m, asian_range, monitor_start_index, direction, config)
        if outcome is not None:
            results.append(outcome)
    return results
