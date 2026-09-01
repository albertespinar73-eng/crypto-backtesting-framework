from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dax_model.models import Candle

CET = ZoneInfo("Europe/Berlin")


def dt(day: int, hour: int, minute: int, month: int = 8, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=CET)


def candle(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    assert l <= o <= h and l <= c <= h, f"OHLC inconsistente: O={o} H={h} L={l} C={c}"
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c)
