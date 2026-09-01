from __future__ import annotations

from helpers import candle, dt

from dax_model.sessions import AsianSessionConfig, KillzoneConfig, compute_asian_range, is_in_killzone


def test_compute_asian_range():
    candles = [
        candle(dt(17, 23, 0), 95, 100, 95, 98),
        candle(dt(17, 23, 5), 95, 97, 90, 92),
    ]
    r = compute_asian_range(candles, AsianSessionConfig(open_time_cet=candles[0].timestamp.timetz().replace(tzinfo=None)))
    assert r.high == 100
    assert r.low == 90
    assert r.equilibrium == 95
    assert r.start_index == 0
    assert r.end_index == 2


def test_is_in_killzone():
    kz = KillzoneConfig()
    assert is_in_killzone(dt(18, 8, 15), kz) is True
    assert is_in_killzone(dt(18, 10, 45), kz) is True
    assert is_in_killzone(dt(18, 8, 14), kz) is False
    assert is_in_killzone(dt(18, 10, 46), kz) is False
