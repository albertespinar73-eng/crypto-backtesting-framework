from __future__ import annotations

from datetime import datetime, timezone

from dax_model.entry import EntryPolicy, choose_entry
from dax_model.models import FVG, FvgType


def _fvg(top: float, bottom: float) -> FVG:
    return FVG(
        fvg_type=FvgType.BEARISH,
        candle1_index=0,
        candle2_index=1,
        candle3_index=2,
        top=top,
        bottom=bottom,
        formed_at=datetime(2026, 8, 18, 8, 30, tzinfo=timezone.utc),
    )


def test_choose_entry_falls_back_to_next_fvg_when_first_exceeds_cap():
    origin = 200.0
    # FVG cercano al precio actual: incluso su borde más profundo (120) está a 80pts de origin
    fvg_near_price = _fvg(top=120, bottom=100)  # borde más cercano a origin=120, distancia=80 > 70
    fvg_near_origin = _fvg(top=160, bottom=140)  # borde más cercano a origin=160, distancia=40 <= 70

    entry = choose_entry([fvg_near_price, fvg_near_origin], origin, EntryPolicy(max_sl_points=70))

    assert entry is not None
    assert entry.fvg is fvg_near_origin
    assert entry.price == 160
    assert entry.stop_distance_points == 40
    assert entry.fvg_rank == 1  # se descartó el primero (más cercano al precio) por exceder el cap


def test_choose_entry_takes_deepest_point_of_valid_fvg():
    # Replica el caso "SL~60" del Apéndice A: un único FVG amplio, la entrada
    # se coloca en el borde más profundo (más cercano al origen), no en el punto medio.
    origin = 25145.0  # origen del leg (último HL roto)
    fvg = _fvg(top=25105, bottom=25020)  # borde superior (más cercano a origin) a 40pts

    entry = choose_entry([fvg], origin, EntryPolicy(max_sl_points=70))

    assert entry is not None
    assert entry.price == 25105
    assert entry.stop_distance_points == 40
    assert entry.fvg_rank == 0


def test_choose_entry_returns_none_when_no_fvg_fits_cap():
    origin = 200.0
    fvg = _fvg(top=100, bottom=80)  # distancia mínima = 100 > 70
    assert choose_entry([fvg], origin, EntryPolicy(max_sl_points=70)) is None
