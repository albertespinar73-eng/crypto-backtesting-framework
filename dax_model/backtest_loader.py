"""Loader para `Full Backtest.numbers` (263 operaciones reales, fuente de
verdad para calibrar cualquier umbral numérico — ver docs/OPEN_QUESTIONS.md).

Confirmado contra el archivo real (18-ago-2026): 1 hoja, 1 tabla, 264 filas
(263 operaciones + cabecera), 20 columnas: `Date, Trade, Day of Week, Order
Type, Asian High/Low Sweep, Lot Size, Opening Time, Closing Time, Duration,
SL, TP, RR, Close, G/L, Total, Percentage, Asian Range, <15m>, 1H, 4H`. OJO:
la cabecera de la columna de 15 minutos no es el texto "15m" sino un
`datetime.timedelta(seconds=900)` — probablemente una celda con formato de
duración en el Numbers original — así que acceder a ella por nombre literal
`'15m'` falla; usa la posición (`header[17]`) o compara por tipo. Es un
diario de resultados (SL/TP/RR planeados, hora, motivo de cierre, sesgo de
estructura etiquetado a mano en 227 de 263 filas), **no** una serie de
velas OHLC — no permite reproducir sweeps/MSS/FVG vela a vela, solo
calibrar umbrales agregados (rango de SL, tasas de alineación, etc.), que
ya se ha hecho para `EntryPolicy.max_sl_points` — ver docs/OPEN_QUESTIONS.md.

Nota de instalación (ya avisada en el brief original): `pip install snappy`
instala el paquete equivocado (topología SnapPy) y rompe `numbers-parser`.
Usa `pip install python-snappy` si hace falta soporte de compresión, y
`numbers-parser` para leer el `.numbers` en sí (ver requirements.txt).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoricalTrade:
    """Una fila de `Full Backtest.numbers`, tal cual está registrada — sin
    normalizar todavía a `dax_model.models.Setup`. El mapeo columna->campo
    depende del esquema real de la hoja, que no se ha podido inspeccionar
    sin el archivo."""

    raw_row: dict[str, object]


def load_full_backtest(path: str | Path) -> list[HistoricalTrade]:
    """Lee `Full Backtest.numbers` con `numbers-parser` y devuelve las filas
    crudas de la tabla de operaciones.

    Se implementa la lectura genérica (primera tabla de la primera hoja);
    una vez se tenga el archivo real, ajustar `sheet_name`/`table_name` si
    hace falta apuntar a una pestaña concreta.
    """
    try:
        from numbers_parser import Document
    except ImportError as exc:  # pragma: no cover - mensaje de ayuda, no lógica
        raise ImportError(
            "Falta numbers-parser. Instala con `pip install numbers-parser` "
            "(NO `pip install snappy` — ese paquete es SnapPy, de topología, "
            "y rompe numbers-parser; usa `python-snappy` si necesitas ese codec)."
        ) from exc

    doc = Document(str(path))
    sheet = doc.sheets[0]
    table = sheet.tables[0]
    header = [cell.value for cell in table.rows()[0]]
    rows = []
    for row in table.rows()[1:]:
        values = [cell.value for cell in row]
        rows.append(HistoricalTrade(raw_row=dict(zip(header, values))))
    return rows
