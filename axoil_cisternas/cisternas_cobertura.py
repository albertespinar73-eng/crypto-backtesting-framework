"""
cisternas_cobertura.py

Motor de cálculo de cobertura de cisternas — puerto Python de la
'Especificación funcional — Flujo de cobertura de cisternas' v2 (07/09/2026).

No depende de Excel ni de Claude for Excel para ejecutarse: consume un
DataFrame con la misma forma que la tabla Cisterna_sheet y una lista de
pedidos vivos, y devuelve la proyección de lotes y el resultado del
matching.

Resuelve, respecto al Excel, la deuda técnica documentada como
"no corregido — requisito del sistema nuevo":
  - §5.1 Asimetría R5/TEPSA: aquí se corrige igual para todos los productos.
  - §5.2 Agujero de la columna C: los lotes son un campo derivado + assert,
    no una fórmula que se pueda quedar vacía en silencio.
  - §6 Semántica en colores: es_reservada, permite_pendiente_negativo,
    redondea_lotes y estado son campos explícitos, no formato condicional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 1. CONSTANTES DEL SISTEMA (spec §8)
# ---------------------------------------------------------------------------

LOTE_M3 = 118.35
TOL_CASADO_M3 = 2.0
LITROS_POR_M3 = 1000

PROD_COBERTURA: dict[str, list[str]] = {
    "GoA": ["GoA", "GASOIL_A_B7", "GOA_55", "GOA_55d"],
    "GoB": ["GoB"],
    "GoC": ["GoC", "GASOLEO_EMBARCACIONES"],  # llega como texto -> to_number
    "Gn95": ["Gn95", "Gn95_23"],
    "Gn98": ["Gn98"],
}

# Columnas del report que NO cuentan para cobertura pero SÍ para el volumen
# por cliente usado en el matching (son dos agregaciones distintas, spec §2.1)
EXCLUIDAS_COBERTURA = [
    "FAME_DC", "FAME_SC", "FAME_DC_ADVANCE", "HVO",
    "GOA_ANTIFRIO_DECAL", "A05", "GASOLEO_C_DMA",
]

ALMACENES_AJUSTE = ["TEPSA BARCELONA", "TEPSA BILBAO"]

EXCLUIDOS_R5 = {
    "GoA": ["R5 ENERGÍA POWER, S.L (ANTICIPADO)"],
    "GoB": ["R5 PETROLEUM POWER, S.L UNIP. (ANTICIPADO)"],
    "GoC": [],
    "Gn95": [],
    "Gn98": [],
}

SUFIJOS_PAGO = ["(ANTICIPADO)", "(CONTADO)", "(CONTADO-FACTURA)", "(3 DIAS)"]


# ---------------------------------------------------------------------------
# 2. MODELOS DE DATOS (spec §6 — campos explícitos, no colores)
# ---------------------------------------------------------------------------

class EstadoFila(str, Enum):
    PENDIENTE_SIN_REPORTAR = "pendiente_sin_reportar"
    PARCIAL = "parcial"
    CASADO = "casado"


class EstadoAlias(str, Enum):
    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"


@dataclass
class AliasEntry:
    """Fila de la tabla Alias Clientes (spec §2.3, §5.7)."""
    alias: str
    razones_sociales: list[str] = field(default_factory=list)
    almacenes: list[str] = field(default_factory=list)
    regla_agregacion: str = ""
    aviso: str = ""
    estado: EstadoAlias = EstadoAlias.PENDIENTE
    fecha_confirmacion: Optional[datetime] = None


@dataclass
class PedidoRow:
    """Fila viva del bloque manual (antes 'Vendas Cisternas' filas 20-131)."""
    alias: str
    m3_total: float                      # columna B
    m3_reportados: float = 0.0           # columna D
    es_reservada: bool = False           # spec §5.3 — nunca se borra
    permite_pendiente_negativo: bool = False  # spec §5.4 — solo petrem
    redondea_lotes: bool = False         # spec §5.4 — solo petrem
    nota_pedido: str = ""
    hora: Optional[datetime] = None
    comercial: str = ""
    estado: EstadoFila = EstadoFila.PENDIENTE_SIN_REPORTAR

    @property
    def m3_pendientes(self) -> float:
        return self.m3_total - self.m3_reportados

    @property
    def lotes(self) -> float:
        pendiente = self.m3_pendientes
        return round(pendiente / LOTE_M3) if self.redondea_lotes else pendiente / LOTE_M3


# ---------------------------------------------------------------------------
# 3. NORMALIZACIÓN (spec §4.3 — tolerancias de matching)
# ---------------------------------------------------------------------------

def to_number(value) -> float:
    """Equivalente a NUMBERVALUE() para GASOLEO_EMBARCACIONES (llega como texto)."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", ".").strip())


def normalizar_cliente(nombre: str) -> str:
    """Trim + colapsa espacios + quita sufijos de condición de pago + upper.
    Cubre las tolerancias obligatorias de §4.3 (mayúsculas, espacios, sufijos).
    NO hace matching difuso: eso vive solo en la tabla de alias (§4.3: 'coincidencia
    difusa automática: NO')."""
    if nombre is None:
        return ""
    n = " ".join(str(nombre).split())
    for sufijo in SUFIJOS_PAGO:
        n = n.replace(sufijo, "")
    return " ".join(n.split()).upper()


def load_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el DataFrame leído de la tabla Cisterna_sheet (21 columnas, spec §2.1).
    Filas sin CODIGO_CLIENTE (el residuo manual de §2.1, filas 283-288 en el Excel)
    quedan fuera a propósito: el resultado diferirá ~3 L del Excel, y eso es correcto.
    """
    df = df.copy()
    df["GASOLEO_EMBARCACIONES"] = df["GASOLEO_EMBARCACIONES"].apply(to_number)
    df["CLIENTE_NORM"] = df["CLIENTE"].apply(normalizar_cliente)
    df = df[df["CODIGO_CLIENTE"].notna()]
    return df


# ---------------------------------------------------------------------------
# 4. CÁLCULO DE COBERTURA (spec §3.1-§3.3, con el fix de §5.1)
# ---------------------------------------------------------------------------

def total_por_producto(report: pd.DataFrame, producto: str) -> float:
    return sum(report[c].sum() for c in PROD_COBERTURA[producto])


def excluido_por_producto(report: pd.DataFrame, producto: str) -> float:
    clientes = EXCLUIDOS_R5[producto]
    if not clientes:
        return 0.0
    mask = report["CLIENTE"].isin(clientes)
    return sum(report.loc[mask, c].sum() for c in PROD_COBERTURA[producto])


def base_tepsa_por_producto(report: pd.DataFrame, producto: str) -> float:
    """A diferencia del Excel (donde solo B4/GoA corrige el solape con R5,
    spec §5.1), aquí se excluye el cliente de EXCLUIDOS_R5 en TEPSA para
    TODOS los productos por igual."""
    clientes = EXCLUIDOS_R5[producto]
    mask = report["ALMACEN"].isin(ALMACENES_AJUSTE)
    if clientes:
        mask &= ~report["CLIENTE"].isin(clientes)
    return sum(report.loc[mask, c].sum() for c in PROD_COBERTURA[producto])


def neto_por_producto(report: pd.DataFrame, producto: str, factor_tepsa: float = 1.0) -> float:
    total = total_por_producto(report, producto)
    excluido = excluido_por_producto(report, producto)
    base_tepsa = base_tepsa_por_producto(report, producto)
    return total - excluido - base_tepsa + base_tepsa * factor_tepsa


def lotes_reportados(report: pd.DataFrame, factor_tepsa: float = 1.0) -> float:
    total_litros = sum(neto_por_producto(report, p, factor_tepsa) for p in PROD_COBERTURA)
    return (total_litros / LITROS_POR_M3) / LOTE_M3


# ---------------------------------------------------------------------------
# 5. VOLUMEN POR CLIENTE PARA MATCHING (spec §4.2 paso 1)
# ---------------------------------------------------------------------------

def volumen_por_cliente(report: pd.DataFrame) -> pd.Series:
    """Σ(E..U)/1000 agrupado por CLIENTE_NORM. A propósito usa TODAS las
    columnas de producto -- incluidas las excluidas de cobertura -- porque
    la agregación de matching y la de cobertura son criterios distintos
    (spec §2.1, nota bajo la tabla de columnas)."""
    columnas = list(dict.fromkeys(
        [c for cols in PROD_COBERTURA.values() for c in cols] + EXCLUIDAS_COBERTURA
    ))
    tmp = report.copy()
    tmp["_vol_total"] = tmp[columnas].sum(axis=1)
    return tmp.groupby("CLIENTE_NORM")["_vol_total"].sum() / LITROS_POR_M3


# ---------------------------------------------------------------------------
# 6. RESOLUCIÓN DE ALIAS (spec §4.2 paso 2, §5.7)
# ---------------------------------------------------------------------------

def resolver_alias(alias_texto: str, alias_db: dict[str, AliasEntry]) -> Optional[AliasEntry]:
    """Solo devuelve un alias CONFIRMADO. Uno pendiente existe pero no casa
    nada todavía (spec §4.6: el alias solo se confirma contra un report que
    ya contenga esa razón social)."""
    entry = alias_db.get(normalizar_cliente(alias_texto))
    if entry is None or entry.estado == EstadoAlias.PENDIENTE:
        return None
    return entry


def alta_alias_pendiente(alias_texto: str, alias_db: dict[str, AliasEntry], origen: str = "") -> AliasEntry:
    """Da de alta un alias nuevo en estado pendiente (spec §5.7). No casa
    nada; solo existe para que el pedido no se pierda y para generar el
    aviso de 'alias nuevo'."""
    clave = normalizar_cliente(alias_texto)
    entry = AliasEntry(
        alias=alias_texto,
        aviso=f"Alias nuevo {datetime.now():%d/%m/%Y}. Origen: {origen}",
        estado=EstadoAlias.PENDIENTE,
    )
    alias_db[clave] = entry
    return entry


# ---------------------------------------------------------------------------
# 7. REGLA DE DECISIÓN POR FILA (spec §4.4 — tabla completa)
# ---------------------------------------------------------------------------

def aplicar_regla_matching(pedido: PedidoRow, reportado_m3: float) -> EstadoFila:
    """Compara el reportado ACUMULADO (no el pendiente actual) contra
    pedido.m3_total. Actualiza pedido.m3_reportados in-place."""
    if reportado_m3 == 0:
        # "reportado = 0" nunca significa casado; significa que aún no ha
        # llegado (spec §4.6). No tocar la fila.
        return EstadoFila.PENDIENTE_SIN_REPORTAR

    diferencia = pedido.m3_total - reportado_m3

    if pedido.permite_pendiente_negativo:
        # petrem (spec §5.4): se escribe el reportado real aunque supere m3_total
        pedido.m3_reportados = reportado_m3
        return EstadoFila.CASADO if diferencia <= TOL_CASADO_M3 else EstadoFila.PARCIAL

    if reportado_m3 >= pedido.m3_total:
        pedido.m3_reportados = pedido.m3_total  # capado: nunca pendiente negativo
        return EstadoFila.CASADO

    if diferencia > TOL_CASADO_M3:
        pedido.m3_reportados = reportado_m3
        return EstadoFila.PARCIAL

    # diferencia <= TOL_CASADO_M3 -> "el resto es polvo"
    pedido.m3_reportados = reportado_m3
    return EstadoFila.CASADO


# ---------------------------------------------------------------------------
# 8. PROCESO DE REFRESH (spec §4.6, §8 "Proceso B")
# ---------------------------------------------------------------------------

def procesar_refresh(
    pedidos_vivos: list[PedidoRow],
    report: pd.DataFrame,
    alias_db: dict[str, AliasEntry],
) -> dict:
    """
    Ejecuta un ciclo de matching contra un refresh del report.
    Las filas reservadas (spec §5.3) nunca se borran: si salen CASADO se
    dejan en 'vivos' igualmente, solo con D actualizado.
    """
    if "CLIENTE_NORM" not in report.columns:
        report = load_report(report)
    volumen_cliente = volumen_por_cliente(report)

    casados, vivos, avisos = [], [], []

    for pedido in pedidos_vivos:
        alias_entry = resolver_alias(pedido.alias, alias_db)

        if alias_entry is None:
            if normalizar_cliente(pedido.alias) not in alias_db:
                alta_alias_pendiente(pedido.alias, alias_db, origen="refresh")
                avisos.append(f"Alias nuevo detectado, dado de alta como PENDIENTE: {pedido.alias}")
            vivos.append(pedido)  # sin alias confirmado, la fila sigue viva (§4.6)
            continue

        reportado_m3 = sum(
            volumen_cliente.get(normalizar_cliente(rs), 0.0)
            for rs in alias_entry.razones_sociales
        )
        pedido.estado = aplicar_regla_matching(pedido, reportado_m3)

        if pedido.estado == EstadoFila.CASADO and not pedido.es_reservada:
            casados.append(pedido)
        else:
            # reservadas nunca se borran (§5.3), aunque estén en estado CASADO
            vivos.append(pedido)

    return {"casados": casados, "vivos": vivos, "avisos": avisos}


# ---------------------------------------------------------------------------
# 9. VERIFICACIÓN DE INVARIANTES (spec §4.5, §5.2 — sustituye al fallo
#    silencioso de la columna C: aquí el proceso falla explícito)
# ---------------------------------------------------------------------------

def verificar_invariantes(pedidos: list[PedidoRow]) -> None:
    for p in pedidos:
        if p.m3_total and p.lotes is None:
            raise AssertionError(f"Fila con volumen sin lotes calculados: {p.alias}")
        if p.m3_pendientes < 0 and not p.permite_pendiente_negativo:
            raise AssertionError(f"Pendiente negativo no permitido en: {p.alias}")


# ---------------------------------------------------------------------------
# 10. PROYECCIÓN FINAL (spec §3.4, §8)
# ---------------------------------------------------------------------------

def proyeccion_lotes(report: pd.DataFrame, pedidos_vivos: list[PedidoRow], factor_tepsa: float = 1.0) -> dict:
    reportados = lotes_reportados(report, factor_tepsa)
    pendientes = sum(p.lotes for p in pedidos_vivos)
    return {
        "lotes_reportados": reportados,
        "lotes_pendientes": pendientes,
        "proyeccion_total": reportados + pendientes,
    }


def lotes_por_cubrir(proyeccion_total: float, objetivo_lotes: float) -> float:
    return proyeccion_total - objetivo_lotes
