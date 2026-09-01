from __future__ import annotations

from helpers import candle, dt

from dax_model.be_rule import BreakevenPolicy, check_breakeven
from dax_model.models import Direction


def test_breakeven_requires_both_1r_and_bos_close():
    # Short trade: entry=100, SL=110 (riesgo=10 pts). reference_level = último swing relevante = 95.
    candles = [
        candle(dt(18, 8, 30), 100, 101, 95, 96),  # close 96: solo 0.4R, no cumple 1R todavía
        candle(dt(18, 8, 35), 96, 97, 88, 89),  # close 89: 1.1R, pero SIN BoS de 5m por cierre bajo 95 confirmado aquí
    ]
    # índice0: 1R aún no alcanzado
    assert check_breakeven(candles, Direction.SHORT, entry_price=100, stop_loss=110, reference_level=95, current_index=0, search_start_index=0) is False

    # índice1: R>1 Y cierre (89) < reference_level (95) -> BoS confirmado -> BE
    assert check_breakeven(candles, Direction.SHORT, entry_price=100, stop_loss=110, reference_level=95, current_index=1, search_start_index=0) is True


def test_breakeven_false_when_r_below_threshold_even_with_bos():
    candles = [
        candle(dt(18, 8, 30), 100, 101, 92, 94),  # close 94: 0.6R, y ya rompe 95 por cierre... pero R insuficiente
    ]
    result = check_breakeven(
        candles, Direction.SHORT, entry_price=100, stop_loss=110, reference_level=95, current_index=0, search_start_index=0, policy=BreakevenPolicy(min_r_multiple=1.0)
    )
    assert result is False
