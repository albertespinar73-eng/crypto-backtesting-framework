from __future__ import annotations

from helpers import candle, dt

from dax_model.detector import DetectorConfig, detect_primary_setups
from dax_model.entry import EntryPolicy
from dax_model.htf_filter import M15FilterPolicy
from dax_model.models import DiscardedSetup, Direction, Setup, SetupModel
from dax_model.sessions import AsianRange


def _candles_5m():
    return [
        candle(dt(17, 23, 0), 95, 100, 95, 98),  # 0: asian range
        candle(dt(17, 23, 5), 95, 97, 90, 92),  # 1: asian range
        candle(dt(18, 7, 0), 90, 93, 89, 91),  # 2: low pivot (89)
        candle(dt(18, 7, 5), 94, 97, 93, 95),  # 3: high pivot (97)
        candle(dt(18, 7, 10), 92, 95, 91, 93),  # 4: HL pivot (91) <- reference level
        candle(dt(18, 7, 15), 94, 96, 94, 95),  # 5
        candle(dt(18, 8, 20), 95, 102, 95, 97),  # 6: SWEEP (asian high=100 broken), origin=102
        candle(dt(18, 8, 25), 97, 98, 92, 93),  # 7: displacement, no MSS yet (93 > 91)
        candle(dt(18, 8, 30), 93, 93, 80, 82),  # 8: MSS confirmed (82 < 91)
    ]


def _candles_15m():
    return [
        candle(dt(18, 6, 45), 96, 100, 95, 98),
        candle(dt(18, 7, 0), 97, 98, 90, 93),
        candle(dt(18, 7, 15), 95, 99, 94, 96),
        candle(dt(18, 7, 30), 89, 97, 88, 89),  # bias -> SHORT before the 08:30 MSS
    ]


def _asian_range():
    return AsianRange(high=100, low=90, equilibrium=95, start_index=0, end_index=2)


def test_detect_primary_short_setup_end_to_end():
    setups = detect_primary_setups(_candles_5m(), _candles_15m(), _asian_range(), monitor_start_index=2)

    shorts = [s for s in setups if isinstance(s, Setup) and s.direction == Direction.SHORT]
    assert len(shorts) == 1
    setup = shorts[0]

    assert setup.model == SetupModel.PRIMARY_SWEEP
    assert setup.sweep_index == 6
    assert setup.mss_index == 8
    assert setup.entry.price == 95  # borde del FVG más cercano al origen (102)
    assert setup.entry.stop_loss == 102
    assert setup.entry.stop_distance_points == 7
    assert setup.take_profit == 95 - 7 * 2
    assert setup.m15_aligned is True


def test_sl_cap_discards_setup_when_no_fvg_fits():
    config = DetectorConfig(entry_policy=EntryPolicy(max_sl_points=5))  # el único FVG está a 7pts del origen
    setups = detect_primary_setups(_candles_5m(), _candles_15m(), _asian_range(), monitor_start_index=2, config=config)

    shorts = [s for s in setups if s.direction == Direction.SHORT]
    assert len(shorts) == 1
    assert isinstance(shorts[0], DiscardedSetup)
    assert shorts[0].reason.code == "SL_EXCEEDS_MAX"


def test_m15_skip_policy_discards_misaligned_setup():
    # Invertimos el sesgo de 15m para que quede en contra del short detectado
    candles_15m_long_bias = [
        candle(dt(18, 6, 45), 90, 95, 89, 91),
        candle(dt(18, 7, 0), 91, 99, 90, 98),  # pivot high candidate (99)
        candle(dt(18, 7, 15), 96, 97, 92, 93),  # confirms pivot
        candle(dt(18, 7, 30), 93, 101, 92, 100),  # close 100 > 99 -> bias LONG
    ]
    config = DetectorConfig(m15_policy=M15FilterPolicy(mode="skip"))
    setups = detect_primary_setups(_candles_5m(), candles_15m_long_bias, _asian_range(), monitor_start_index=2, config=config)

    shorts = [s for s in setups if s.direction == Direction.SHORT]
    assert len(shorts) == 1
    assert isinstance(shorts[0], DiscardedSetup)
    assert shorts[0].reason.code == "M15_MISALIGNED"
