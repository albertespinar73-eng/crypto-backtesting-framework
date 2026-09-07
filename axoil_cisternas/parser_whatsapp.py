"""
parser_whatsapp.py

Convierte el texto pegado de WhatsApp (uno o varios mensajes seguidos, con
sus cabeceras [hora, fecha] Comercial - Axoil: ...) en una lista de
PedidoRow, siguiendo las reglas de la spec §5.8:

  - Números negativos = descuento del comercial, nunca cantidad. No entran
    en el volumen del pedido.
  - Litros -> m3 (dividir entre 1000). Si viene en 'M3' o en 'mil' (de
    litros), el número ya representa directamente los m3.
  - Ampliaciones al mismo producto dentro del mismo mensaje se suman.
  - Cliente nuevo / alias no reconocido: no es tarea de este módulo — lo
    resuelve resolver_alias()/alta_alias_pendiente() en cisternas_cobertura.py
    cuando se procesa el refresh. Aquí solo se guarda el alias tal cual llegó.

Basado en ejemplos reales:
    "Aoil trans\n32 mil de GA\n-7"
        -> alias "Aoil trans", GoA: 32 m3, descuento -7 (ignorado)
    "GONDELCU SL\n26M3 GOA \n10M3 GN95\nTARIFA CON -2"
        -> alias "GONDELCU SL", GoA: 26 m3, Gn95: 10 m3
    "ARBERE\n2 x 4.000 de A\n2 x 10.000 de B\n4.000 de B\n-5"
        -> alias "ARBERE", GoA: 8 m3, GoB: 24 m3 (20 + 4, ampliación sumada)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from cisternas_cobertura import PedidoRow

# ---------------------------------------------------------------------------
# Cabecera de mensaje de WhatsApp: "[13:19, 4/9/2026] Inma Córdoba - Axoil: "
# ---------------------------------------------------------------------------

HEADER_RE = re.compile(
    r'^\[(?P<hora>\d{1,2}:\d{2}),\s*(?P<fecha>\d{1,2}/\d{1,2}/\d{4})\]\s*'
    r'(?P<remitente>[^:]+):\s*(?P<resto>.*)$'
)


def split_mensajes(texto_bloque: str) -> list[dict]:
    """Separa un bloque con varios mensajes de WhatsApp en mensajes individuales."""
    mensajes: list[dict] = []
    actual: Optional[dict] = None

    for linea in texto_bloque.splitlines():
        m = HEADER_RE.match(linea)
        if m:
            if actual is not None:
                mensajes.append(actual)
            comercial = m.group("remitente").split(" - ")[0].strip()
            try:
                hora = datetime.strptime(
                    f"{m.group('fecha')} {m.group('hora')}", "%d/%m/%Y %H:%M"
                )
            except ValueError:
                hora = None
            primera = m.group("resto").strip()
            actual = {
                "comercial": comercial,
                "hora": hora,
                "lineas": [primera] if primera else [],
            }
        elif actual is not None and linea.strip():
            actual["lineas"].append(linea.strip())

    if actual is not None:
        mensajes.append(actual)

    # Si no había ninguna cabecera (se pegó solo el cuerpo del mensaje, sin
    # el "[hora] Comercial - Axoil:"), tratar todo el bloque como un único
    # mensaje sin metadatos.
    if not mensajes and texto_bloque.strip():
        mensajes = [{
            "comercial": "",
            "hora": None,
            "lineas": [l.strip() for l in texto_bloque.splitlines() if l.strip()],
        }]

    return mensajes


# ---------------------------------------------------------------------------
# Detección de cantidades y productos
# ---------------------------------------------------------------------------

PRODUCTO_MAP = {
    "GOA": "GoA", "GA": "GoA", "A": "GoA",
    "GOB": "GoB", "GB": "GoB", "B": "GoB",
    "GOC": "GoC", "GC": "GoC", "C": "GoC",
    "GN95": "Gn95", "95": "Gn95",
    "GN98": "Gn98", "98": "Gn98",
}

# Orden importa: alternativas más largas/específicas primero.
CANTIDAD_RE = re.compile(
    r'(?:(?P<mult>\d+)\s*[x×]\s*)?'          # "2 x " opcional
    r'(?P<cantidad>\d[\d.,]*)\s*'             # número, admite miles con "."
    r'(?P<unidad>m3|mil)?\s*'                 # unidad opcional
    r'(?:de\s+)?'                             # "de" opcional
    r'(?P<producto>GOA|GOB|GOC|GN95|GN98|GA|GB|GC|[ABC]|95|98)\b',
    re.IGNORECASE,
)

DESCUENTO_STANDALONE_RE = re.compile(r'^-\d+(?:[.,]\d+)?\s*(€|EUR)?$', re.IGNORECASE)
DESCUENTO_TARIFA_RE = re.compile(r'-\d+(?:[.,]\d+)?', re.IGNORECASE)


def es_linea_descuento(linea: str) -> bool:
    limpio = linea.strip()
    if DESCUENTO_STANDALONE_RE.match(limpio):
        return True
    if "tarifa" in limpio.lower() and DESCUENTO_TARIFA_RE.search(limpio):
        return True
    return False


def _parse_num(texto: str) -> float:
    """'4.000' -> 4000.0 ; '26' -> 26.0 ; '10,5' -> 10.5 (formato español)."""
    limpio = texto.strip()
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    else:
        limpio = limpio.replace(".", "")
    return float(limpio)


def parsear_cantidades(lineas: list[str]) -> tuple[dict[str, float], list[str]]:
    """
    Devuelve (cantidades_por_producto_en_m3, lineas_no_reconocidas).
    Las ampliaciones al mismo producto dentro del mismo mensaje se suman.
    """
    cantidades: dict[str, float] = {}
    no_reconocidas: list[str] = []

    for linea in lineas:
        match = CANTIDAD_RE.search(linea)
        if not match:
            no_reconocidas.append(linea)
            continue

        cantidad = _parse_num(match.group("cantidad"))
        mult = int(match.group("mult")) if match.group("mult") else 1
        unidad = (match.group("unidad") or "").lower()
        producto = PRODUCTO_MAP.get(match.group("producto").upper())

        if producto is None:
            no_reconocidas.append(linea)
            continue

        total = cantidad * mult
        # 'm3' y 'mil' (miles de litros) representan directamente el valor en m3;
        # sin unidad se asume litros -> dividir entre 1000.
        m3 = total if unidad in ("m3", "mil") else total / 1000

        cantidades[producto] = cantidades.get(producto, 0.0) + m3

    return cantidades, no_reconocidas


# ---------------------------------------------------------------------------
# Ensamblado del pedido
# ---------------------------------------------------------------------------

def parsear_mensaje(mensaje: dict) -> PedidoRow:
    cantidades, no_reconocidas = parsear_cantidades(mensaje["lineas"])

    alias = None
    for linea in no_reconocidas:
        if es_linea_descuento(linea):
            continue
        if not linea.strip():
            continue
        alias = linea.strip()
        break  # la primera línea "no numérica" es el alias, spec: primera línea del mensaje

    desglose = ", ".join(f"{p}: {m3:.2f} m3" for p, m3 in cantidades.items())
    nota = "\n".join(mensaje["lineas"])
    if desglose:
        nota += f"\n[desglose detectado: {desglose}]"

    return PedidoRow(
        alias=alias or "(alias no detectado — revisar manualmente)",
        m3_total=round(sum(cantidades.values()), 3),
        nota_pedido=nota,
        hora=mensaje["hora"],
        comercial=mensaje["comercial"],
    )


def parsear_pedidos_whatsapp(texto_bloque: str) -> list[PedidoRow]:
    """Punto de entrada: pega uno o varios mensajes de WhatsApp, devuelve
    un PedidoRow por mensaje."""
    mensajes = split_mensajes(texto_bloque)
    return [parsear_mensaje(m) for m in mensajes]
