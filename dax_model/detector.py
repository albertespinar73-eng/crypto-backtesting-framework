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

Filtros togglables para backtest A/B (petición explícita de Albert):

- `config.m15_policy.enabled` (default True) — filtro de estructura de 15m.
- `config.h1_policy.enabled` (default False) — filtro de estructura de 1H,
  ver docs/OPEN_QUESTIONS.md #11 (los dos informes de validación no están de
  acuerdo sobre si el 1H sobrevive out-of-sample).
- `config.ma_trend_policy.enabled` (default False) — filtro de tendencia
  SMA100, feature nueva sin validar contra ningún dato todavía.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from .entry import EntryPolicy, choose_entry
from .fvg import find_fvgs, is_mitigated
from .htf_filter import M15FilterPolicy, compute_m15_bias, evaluate_m15_filter
from .models import Candle, DiscardedSetup, DiscardReason, Direction, Entry, Setup, SetupModel
from .sessions import AsianRange, KillzoneConfig, is_in_killzone
from .structure import classify_swings, detect_mss, find_pivots, last_swing_before
from .trend_filter import MATrendFilterPolicy, compute_ma_trend_bias, evaluate_ma_trend_filter
from .models import SwingKind


@dataclass(frozen=True)
class DetectorConfig:
    killzone: KillzoneConfig = KillzoneConfig()
    entry_policy: EntryPolicy = EntryPolicy()
    # Filtro de estructura de 15m — CONFIRMADO por Albert como filtro activo
    # (mode="skip"). Apaga con M15FilterPolicy(enabled=False) para
    # backtestear "sin filtro de estructura" (Albert tiene dudas de que la
    # lectura de market structure sea correcta y quiere poder comparar).
    m15_policy: M15FilterPolicy = M15FilterPolicy()
    # Filtro de estructura de 1H — mismo mecanismo que el de 15m, pero
    # DESACTIVADO por defecto: los dos informes de validación de Albert no
    # coinciden en si el 1H sobrevive out-of-sample (ver htf_filter.py y
    # docs/OPEN_QUESTIONS.md #11). Actívalo para comparar en backtest.
    h1_policy: M15FilterPolicy = M15FilterPolicy(enabled=False)
    # Filtro de tendencia SMA100 — feature nueva sin validar (ver
    # trend_filter.py), desactivado por defecto.
    ma_trend_policy: MATrendFilterPolicy = MATrendFilterPolicy()
    pivot_left: int = 1
    pivot_right: int = 1
    take_profit_rr: float = 2.0
    # CONFIRMADO por Albert (pregunta #5 de docs/OPEN_QUESTIONS.md): tanto el
    # sweep (ver sessions.AsianSessionConfig / inSweepWindow en el indicador
    # Pine) como el MSS tienen que ocurrir DESPUÉS del cierre del rango
    # asiático. El MSS, en concreto, solo cuenta dentro de su propia ventana
    # 08:00-10:30 CET, independiente de la killzone de ejecución (08:15).
    # Fuera de [mss_min_time_cet, mss_max_time_cet] se descarta. Un MSS
    # confirmado entre 08:00 y el inicio de la killzone sigue necesitando que
    # el FVG de entrada no se haya mitigado para cuando la killzone abre y se
    # puede operar de verdad (ver mitigation_check_index más abajo).
    # Sustituye al antiguo `allow_pre_killzone_setups`.
    mss_min_time_cet: time = time(8, 0)
    mss_max_time_cet: time = time(10, 30)


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
    candles_1h: list[Candle],
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
    mss_time_cet = mss_ts.timetz().replace(tzinfo=None)

    if mss_time_cet < config.mss_min_time_cet:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason(
                "MSS_TOO_EARLY",
                f"MSS confirmado antes de las {config.mss_min_time_cet.strftime('%H:%M')} CET",
            ),
        )

    if mss_time_cet > config.mss_max_time_cet:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason(
                "MSS_TOO_LATE",
                f"MSS confirmado después de las {config.mss_max_time_cet.strftime('%H:%M')} CET",
            ),
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

    h1_window = candles_1h[: _index_at_or_before(candles_1h, mss_ts) + 1] if candles_1h else []
    h1_bias = compute_m15_bias(h1_window) if h1_window else None  # función agnóstica al timeframe
    h1_result = evaluate_m15_filter(direction, h1_bias, config.h1_policy)

    if not h1_result.take_trade:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason("H1_MISALIGNED", "Estructura de 1H en contra de la dirección del setup"),
        )

    ma_source = h1_window if config.ma_trend_policy.timeframe == "1h" else m15_window
    ma_trend_bias = compute_ma_trend_bias(ma_source, config.ma_trend_policy.period) if ma_source else None
    ma_trend_result = evaluate_ma_trend_filter(direction, ma_trend_bias, config.ma_trend_policy)

    if not ma_trend_result.take_trade:
        return DiscardedSetup(
            model=SetupModel.PRIMARY_SWEEP,
            direction=direction,
            sweep_index=sweep_index,
            reason=DiscardReason(
                "MA100_TREND_MISALIGNED",
                f"Precio en contra de la SMA{config.ma_trend_policy.period} en {config.ma_trend_policy.timeframe}",
            ),
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
        h1_aligned=h1_result.aligned,
        ma_trend_aligned=ma_trend_result.aligned,
    )


def detect_primary_setups(
    candles_5m: list[Candle],
    candles_15m: list[Candle],
    asian_range: AsianRange,
    monitor_start_index: int,
    config: DetectorConfig = DetectorConfig(),
    candles_1h: list[Candle] | None = None,
) -> list[Setup | DiscardedSetup]:
    """Evalúa ambas direcciones (barrido de Asian High -> short, barrido de
    Asian Low -> long) para una sesión y devuelve lo que haya encontrado.
    `monitor_start_index` es el índice en `candles_5m` a partir del cual
    empieza a monitorizarse el sweep (recomendado: justo tras el cierre del
    rango asiático, ver sessions.compute_asian_range).

    `candles_1h` es opcional (por defecto `[]`) porque el filtro de 1H está
    desactivado por defecto (`config.h1_policy.enabled=False`) — solo hace
    falta pasarlo si se activa para comparar en backtest.
    """
    results: list[Setup | DiscardedSetup] = []
    for direction in (Direction.SHORT, Direction.LONG):
        outcome = _evaluate_direction(
            candles_5m, candles_15m, candles_1h or [], asian_range, monitor_start_index, direction, config
        )
        if outcome is not None:
            results.append(outcome)
    return results
