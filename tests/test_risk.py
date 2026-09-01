from __future__ import annotations

import pytest

from dax_model.risk import (
    DailyLimiter,
    DrawdownGuardrail,
    DrawdownLimits,
    DrawdownState,
    InstrumentSpec,
    position_size,
)


def test_position_size_uses_one_percent_risk():
    size = position_size(equity=10_000, stop_distance_points=50, spec=InstrumentSpec(point_value=1.0))
    # 1% de 10000 = 100; 100/50 = 2.0
    assert size == pytest.approx(2.0)


def test_position_size_rejects_stop_beyond_cap():
    with pytest.raises(ValueError):
        position_size(equity=10_000, stop_distance_points=71, spec=InstrumentSpec(max_stop_points=70))


def test_daily_limiter_stops_after_first_loss():
    limiter = DailyLimiter()
    limiter.reset_if_new_day(today=__import__("datetime").date(2026, 8, 18))
    assert limiter.can_trade() is True

    limiter.record_trade_result(r_multiple=-1.0)
    assert limiter.can_trade() is False  # parada tras la primera pérdida, aunque quede cupo


def test_daily_limiter_caps_at_two_trades_even_if_winning():
    limiter = DailyLimiter()
    limiter.reset_if_new_day(today=__import__("datetime").date(2026, 8, 18))
    limiter.record_trade_result(r_multiple=2.0)
    assert limiter.can_trade() is True
    limiter.record_trade_result(r_multiple=2.0)
    assert limiter.can_trade() is False


def test_daily_limiter_resets_on_new_day():
    limiter = DailyLimiter()
    day1 = __import__("datetime").date(2026, 8, 18)
    day2 = __import__("datetime").date(2026, 8, 19)
    limiter.reset_if_new_day(today=day1)
    limiter.record_trade_result(r_multiple=-1.0)
    assert limiter.can_trade() is False
    limiter.reset_if_new_day(today=day2)
    assert limiter.can_trade() is True


def test_drawdown_guardrail_states():
    guardrail = DrawdownGuardrail(limits=DrawdownLimits(daily_limit_pct=0.05, total_limit_pct=0.10, warning_threshold_pct=0.80))
    guardrail.start_new_day(equity=10_000)

    assert guardrail.evaluate(current_equity=10_000) == DrawdownState.ACTIVE
    # 4.5% de drawdown diario = 90% del límite del 5% -> WARNING
    assert guardrail.evaluate(current_equity=9_550) == DrawdownState.WARNING
    # 5% de drawdown diario = 100% del límite -> HALTED
    assert guardrail.evaluate(current_equity=9_500) == DrawdownState.HALTED
