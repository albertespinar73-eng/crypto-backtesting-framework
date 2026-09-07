"""
app_cobertura.py

Panel de control para el flujo de cobertura de cisternas.
Sustituye el "refresh manual del sheet" + "pegar en el bloque manual" del
Excel por una pantalla única.

Ejecutar con:  streamlit run app_cobertura.py

Requiere: streamlit, pandas, y el módulo cisternas_cobertura.py en el mismo
directorio (o instalado en el path).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from parser_whatsapp import parsear_pedidos_whatsapp
from cisternas_cobertura import (
    AliasEntry,
    EstadoAlias,
    PedidoRow,
    procesar_refresh,
    proyeccion_lotes,
    lotes_por_cubrir,
    verificar_invariantes,
)

# ---------------------------------------------------------------------------
# FUENTE DE DATOS — TODO: reemplazar por la conexión real
# ---------------------------------------------------------------------------
# Hoy esto lo alimenta la consulta Power Query "Cisterna sheet". Hay que
# sustituir esta función por la llamada directa a esa misma fuente
# (SQL / API / lo que sea). Debe devolver un DataFrame con las 21 columnas
# de la spec §2.1 (ALMACEN, CODIGO_ALMACEN, CODIGO_CLIENTE, CLIENTE, GoA...Gn95_23).

import xlwings as xw  # pip install xlwings

# Excel sigue haciendo su propio refresh (Power Query cada 15 min, con el
# libro abierto). Python NO se conecta a EfiOil directamente por ahora:
# solo lee lo que ya está calculado en la hoja "Report Cisternes" del Excel
# abierto. Cuando quieras independizarte del todo de Excel, el conector
# directo a EfiOil (pyodbc) queda como paso futuro, no aquí.

SHEET_REPORT = "Report Cisternes"
TABLA_REPORT = "Cisterna_sheet"  # nombre de la tabla de Excel — confirmar si difiere


def fetch_report_from_excel(workbook_name: str | None = None) -> pd.DataFrame:
    """
    Lee el Report directamente del libro ABIERTO en Excel.
    - Si workbook_name se deja vacío, usa el libro activo (xw.books.active).
    - Intenta leer la tabla con nombre 'Cisterna_sheet'; si el nombre no
      coincide, cae al rango usado completo de la hoja como respaldo.
    """
    wb = xw.books(workbook_name) if workbook_name else xw.books.active
    if wb is None:
        raise RuntimeError(
            "No se ha encontrado el libro en Excel. Asegúrate de que está "
            "abierto (y, si hay varios libros abiertos, indica su nombre)."
        )
    sheet = wb.sheets[SHEET_REPORT]
    try:
        tabla = sheet.tables[TABLA_REPORT]
        df = tabla.range.options(pd.DataFrame, header=1, index=False).value
    except Exception:
        data = sheet.used_range.value
        df = pd.DataFrame(data[1:], columns=data[0])
    return df



# ---------------------------------------------------------------------------
# ESTADO DE SESIÓN
# ---------------------------------------------------------------------------

def init_state():
    if "pedidos_vivos" not in st.session_state:
        st.session_state.pedidos_vivos = []  # list[PedidoRow]
    if "alias_db" not in st.session_state:
        st.session_state.alias_db: dict[str, AliasEntry] = {}
    if "report" not in st.session_state:
        st.session_state.report = None
    if "last_check" not in st.session_state:
        st.session_state.last_check = None
    if "avisos" not in st.session_state:
        st.session_state.avisos = []


init_state()

st.set_page_config(page_title="Cobertura Cisternas", layout="wide")
st.title("Cobertura de cisternas")

# ---------------------------------------------------------------------------
# BLOQUE 1 — CHECK: LEE EL EXCEL YA REFRESCADO Y DISPARA EL CASADO/BORRADO
# ---------------------------------------------------------------------------

workbook_name = st.text_input(
    "Nombre del libro Excel (déjalo vacío para usar el libro activo)",
    value="",
)

col_btn, col_ts = st.columns([1, 3])

with col_btn:
    if st.button("✅ Comprobar y casar", type="primary"):
        try:
            st.session_state.report = fetch_report_from_excel(workbook_name or None)
            st.session_state.last_check = datetime.now()

            resultado = procesar_refresh(
                st.session_state.pedidos_vivos,
                st.session_state.report,
                st.session_state.alias_db,
            )
            st.session_state.pedidos_vivos = resultado["vivos"]
            st.session_state.avisos = resultado["avisos"]

            if resultado["casados"]:
                nombres = ", ".join(p.alias for p in resultado["casados"])
                st.success(f"Casados y retirados: {nombres}")
            else:
                st.info("Sin matches nuevos en esta comprobación.")

        except Exception as e:
            st.error(f"No se pudo leer el Excel: {e}")

with col_ts:
    if st.session_state.last_check:
        st.caption(f"Última comprobación: {st.session_state.last_check:%d/%m/%Y %H:%M:%S}")
    else:
        st.caption("Todavía no se ha comprobado en esta sesión.")

for aviso in st.session_state.avisos:
    st.warning(aviso)

st.divider()

# ---------------------------------------------------------------------------
# BLOQUE 2 — PEGAR PEDIDO DE WHATSAPP
# ---------------------------------------------------------------------------

st.subheader("Nuevo pedido")
texto_pedido = st.text_area(
    "Pega aquí uno o varios mensajes de WhatsApp tal cual (con o sin cabecera [hora] Comercial - Axoil:)",
    height=150,
    placeholder="[13:19, 4/9/2026] Inma Córdoba - Axoil: Aoil trans\n32 mil de GA\n-7",
)

if st.button("🔎 Previsualizar pedido(s)"):
    if texto_pedido.strip():
        st.session_state.preview_pedidos = parsear_pedidos_whatsapp(texto_pedido)
    else:
        st.warning("Pega el texto del pedido antes de procesar.")

if st.session_state.get("preview_pedidos"):
    st.caption("Revisa antes de añadir — sobre todo los que digan 'alias no detectado'.")
    preview_df = pd.DataFrame([
        {
            "Alias": p.alias,
            "m³ total": p.m3_total,
            "Comercial": p.comercial,
            "Hora": p.hora,
        }
        for p in st.session_state.preview_pedidos
    ])
    st.dataframe(preview_df, use_container_width=True)

    if st.button("✅ Confirmar y añadir a pedidos vivos"):
        st.session_state.pedidos_vivos.extend(st.session_state.preview_pedidos)
        st.success(f"{len(st.session_state.preview_pedidos)} pedido(s) añadido(s).")
        st.session_state.preview_pedidos = []

st.divider()

# ---------------------------------------------------------------------------
# BLOQUE 3 — PEDIDOS VIVOS Y PROYECCIÓN
# ---------------------------------------------------------------------------

st.subheader("Pedidos vivos")

if st.session_state.pedidos_vivos:
    tabla = pd.DataFrame([
        {
            "Alias": p.alias,
            "m³ total": p.m3_total,
            "m³ reportados": p.m3_reportados,
            "m³ pendientes": p.m3_pendientes,
            "Lotes": round(p.lotes, 2),
            "Estado": p.estado.value,
            "Reservada": p.es_reservada,
        }
        for p in st.session_state.pedidos_vivos
    ])
    st.dataframe(tabla, use_container_width=True)
else:
    st.caption("No hay pedidos vivos.")

st.subheader("Proyección")

objetivo = st.number_input("Objetivo de lotes del día", min_value=0.0, value=54.0, step=1.0)

if st.session_state.report is not None and st.session_state.pedidos_vivos is not None:
    try:
        verificar_invariantes(st.session_state.pedidos_vivos)
        proy = proyeccion_lotes(st.session_state.report, st.session_state.pedidos_vivos)
        por_cubrir = lotes_por_cubrir(proy["proyeccion_total"], objetivo)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Lotes reportados", f"{proy['lotes_reportados']:.2f}")
        c2.metric("Lotes pendientes", f"{proy['lotes_pendientes']:.2f}")
        c3.metric("Proyección total", f"{proy['proyeccion_total']:.2f}")
        c4.metric("Por cubrir", f"{por_cubrir:.2f}")
    except AssertionError as e:
        st.error(f"Invariante violada: {e}")
else:
    st.caption("Actualiza el report al menos una vez para ver la proyección.")
