# Preguntas abiertas para Albert

Este documento consolida todas las decisiones que el propio prompt de
especificación marca como pendientes de confirmación por Albert antes de
tocar la cuenta real (y, en varios casos, antes de fijar el comportamiento
por defecto en el código). Mientras no se confirmen, el código usa el
**valor por defecto** indicado, expuesto como parámetro configurable — nunca
hardcodeado sin posibilidad de cambio.

Estado: los documentos fuente ya se han subido (18-ago-2026) y se han
incorporado — ver "Calibración con datos reales" más abajo. Varias de las
preguntas de esta tabla ahora tienen un default *calibrado* en vez de un
placeholder; se marcan como tal. Las que dependen de datos de bróker/cuenta
que solo Albert conoce siguen abiertas. No se ha conectado nada a MT4/5 ni a
una cuenta real; esta fase (Fase 0) sigue siendo solo backtest/calibración.

| # | Pregunta | Default actual en código | Dónde vive el parámetro |
|---|----------|---------------------------|--------------------------|
| 1 | Hora exacta de apertura de la sesión nocturna del DAX40 CFD en el bróker real de Albert (inicio del rango asiático; el fin, 06:00 CET, ya está fijado). | `23:00 CET` (placeholder, típico de FXCM/OANDA-style feeds) — **sigue sin confirmar**, ningún documento subido lo especifica. | `dax_model.sessions.AsianSessionConfig.open_time_cet` |
| 2 | Bróker MT4/5 concreto, tipo de cuenta, apalancamiento, valor exacto del punto/tick para el DAX40 CFD. | `point_value=1.0` (1 punto = 1 unidad de cuenta por lote estándar; **sin confirmar**). Los G/L de `Full_Backtest.numbers` son compatibles con ~1 USD/punto/contrato, "CFD-style" según `Asian_Sweep_Paper.pdf` §6 — no una confirmación formal del bróker real. | `dax_model.risk.InstrumentSpec` |
| 3 | Nombre de la prop firm (o cuenta propia) y reglas exactas de drawdown diario/total y tamaño de cuenta. | Placeholder: DD diario 5%, DD total 10%, aviso al 80% del límite — **sigue sin confirmar**. Dato de contexto ahora disponible: sobre las 263 operaciones reales a 1% de riesgo, el riesgo simulado de tocar un 10% de drawdown total es 7.2% (full record) / 5.8% (solo out-of-sample) — ver `docs/RISK_GUARDRAILS.md`. | `dax_model.risk.DrawdownGuardrail` |
| 4 | Precisión de la entrada dentro del FVG. | Se implementa como **el borde del FVG más cercano al origen del leg**, descartando el FVG si ese borde excede el cap. Ver `docs/STRATEGY_SPEC.md#entrada-y-stop-loss`. **El cap en sí ya está CALIBRADO** con datos reales (ver fila siguiente) — la precisión exacta del punto de entrada dentro del hueco sigue siendo la interpretación mecánica más simple, no confirmada vela a vela porque `Full_Backtest.numbers` es un diario de resultados (SL/TP/RR planeados), no una serie de velas OHLC con la que reproducir la entrada exacta. | `dax_model.entry.choose_entry` (`EntryPolicy`) |
| 4bis | Cap de stop loss máximo (`max_sl_points`). | **CALIBRADO**: antes placeholder ~70pts; los 263 SL reales van de 20 a 75 puntos (mediana 40, media 40.8; solo 1 operación >70, ninguna >75). `DAX40_Statistical_Review.pdf` confirma el ensanchamiento explícito de 20–60 a 20–75/25–75 puntos por el régimen de volatilidad 2026 (rango diario medio ~390pt vs ~180–200pt en 2023–24) — decisión de ajuste de régimen, no de backtest. **Nuevo default: 75.0.** | `dax_model.entry.EntryPolicy.max_sl_points`, `dax_model.risk.InstrumentSpec.max_stop_points` |
| 5 | ¿Un setup con MSS+FVG completado antes de las 08:15 CET sigue siendo válido para entrar en cuanto abre la killzone, o solo cuentan los setups completados dentro de 08:15–10:45? | **CONFIRMADO por Albert: tanto el sweep como el MSS tienen que ocurrir DESPUÉS del cierre del rango asiático, y el MSS solo cuenta dentro de su propia ventana, 08:00–10:30 CET** (no hace falta esperar a que abra la killzone de ejecución, 08:15–10:45). Un MSS antes de las 08:00 (`MSS_TOO_EARLY`) o después de las 10:30 (`MSS_TOO_LATE`) se descarta; uno confirmado entre 08:00 y 08:15 sigue exigiendo que el FVG de entrada no se haya mitigado para cuando la killzone abre. Misma regla en el indicador Pine y en `dax_model`. Nota de calibración: `DAX40_Statistical_Review.pdf` usa la ventana 08:15–10:35 (no 10:45) y observa que solo 12 de 261 trades se tomaron fuera de esa ventana — demasiado pocos para testear la regla de la ventana en sí. | `dax_model.detector.DetectorConfig.mss_min_time_cet`/`mss_max_time_cet`, `pine/dax_asian_sweep_mss.pine` (`mssWindowSession`) |
| 6 | Filtro de 15 minutos en contra: ¿se descarta la operación del todo, o se toma con tamaño reducido? | **CONFIRMADO por Albert: descartar (`skip`)**. Reforzado por los datos reales: `Asian_Sweep_Paper.pdf` (el paper completo, versión más rigurosa) confirma que el 15m es "the only conditional finding in this study that survives out-of-sample testing" (+0.93R alineado vs +0.17R en contra, p=5.0×10⁻⁴, 227 trades etiquetados). | `dax_model.htf_filter.M15FilterPolicy` (`enabled`, `"skip"` \| `"reduce"`) |
| 7 | Regla de breakeven definitiva: la del PDF tal cual, o esperar a más datos del estudio de BE. | Regla base del PDF: mover a BE solo si trade > 1R **y** hay BoS de 5m confirmado por cierre. Sin cambios — `BE_Trades_Backtest.pages` no se ha subido todavía. Dato de contexto nuevo: la tasa de trades cerrados en BE ha subido de 6% (2023) a 20% (2026) según `Asian_Sweep_Paper.pdf` §5 (confirma la tendencia 5.6%→19.6% ya mencionada en el brief original) — el EV estimado de esos scratches, si hubieran corrido al 54.9% de tasa de acierto del resto del record, ronda +0.78R cada uno (~+29R en total sobre el record), aunque el propio paper aclara que es una estimación, no un replay real. | `dax_model.be_rule.BreakevenPolicy` |
| 8 | Duración mínima y criterios de salida de la fase demo antes de pasar a real. | Sin definir — **no hay fecha ni nº de operaciones asumido**. Ver `docs/DEPLOYMENT_PLAN.md`. | N/A (decisión de proceso, no de código) |
| 9 | ¿Notificaciones críticas (Telegram/email) para kill-switches/errores, aunque se pidiera "solo dashboard"? | Se recomienda sí como red de seguridad mínima; no implementado todavía (Fase 0 es offline). | Pendiente de diseño en Fase 1 |
| 10 | ¿Journaling también en Notion ("Trading Journal 2026") además de/en vez de SQLite local? | SQLite es la fuente de verdad; export a Notion sería un paso adicional opcional. | Pendiente de diseño en Fase 1 |
| 11 | **NUEVA** — Filtro de estructura de 1H: los dos informes de validación subidos no están de acuerdo. | `Asian_Sweep_Paper.pdf` (el working paper completo, v2, 18-ago-2026) es explícito: es una **autocorrección** de una versión anterior del propio estudio — con solo 52 trades etiquetados, el 1H parecía el efecto dominante; con los 227 trades completos y un test out-of-sample correcto (entrenar en 2023-24, evaluar en 2025-26), "the ranking reverses: the 1-hour effect shrinks by 67%, while the 15-minute effect grows". `DAX40_Quantitative_Validation.pdf` (el resumen ejecutivo del mismo estudio) coincide. `DAX40_Statistical_Review.pdf` (documento distinto, con su propio dataset n=225 y su propio framework de tiers A/A++) SÍ encuentra el 1H significativo (p=0.0038) y lo usa activamente junto al 15m — pero no aplica el mismo split temporal in/out-of-sample a esa alineación concreta. Dado que el working paper es el más riguroso en este punto específico (proper hold-out temporal), el filtro de 1H se implementa **desactivado por defecto**, disponible como toggle para que Albert lo active y compare en backtest si quiere contrastar el framework del Statistical Review. | `dax_model.detector.DetectorConfig.h1_policy` (`M15FilterPolicy(enabled=False)`) |
| 12 | **NUEVA** — Filtro de tendencia SMA100 (15m o 1H), pedido por Albert. | Ninguno de los tres documentos prueba ni menciona un filtro de media móvil — es una feature nueva, sin validar. Implementado **desactivado por defecto**, togglable para backtest A/B, con periodo y timeframe configurables. | `dax_model.trend_filter.MATrendFilterPolicy` (vía `DetectorConfig.ma_trend_policy`) |
| 13 | **NUEVA** — Día de la semana: `DAX40_Statistical_Review.pdf` encuentra que los viernes son un peor desempeño real y significativo (WR 42.6% vs 56–65% el resto de días, p=0.025); recomienda 0.5% de riesgo en viernes hasta que una ventana móvil de 20 trades muestre WR≥57% y PF≥3.0. No implementado todavía — ningún otro documento (ni el brief original de Albert) pide esta regla, y cambiaría el guardrail de "1% fijo siempre" de la Sección 5 del brief. **No se ha añadido sin que Albert lo confirme explícitamente**, ya que contradice una regla que él mismo fijó como no-condicional. | Pendiente de decisión — no implementado |
| 14 | **NUEVA** — La edge del modelo decae con el tiempo: expectancy +1.06R (2023) → +0.87R (2024) → +0.60R (2025) → +0.48R (2026 parcial); tendencia -0.201R/año, p=0.010 (significativo). El out-of-sample (2025-26) sigue siendo rentable y significativo por sí solo (p=1.2×10⁻⁵), pero un 40% por debajo del in-sample. | Informativo — el dashboard de Fase 1 debería mostrar expectancy rodante, no solo acumulada, para poder vigilar si la tendencia continúa. No es un guardrail de código todavía. | Pendiente de diseño en Fase 1 |

## Decisión de arquitectura (Sección 6) — CONFIRMADA

Ver `docs/ARCHITECTURE.md`. **Confirmado por Albert: VPS Windows + EA nativo
en MQL5 para ejecución/gestión de la orden y el kill-switch de drawdown**
(sobrevive aunque el proceso Python se caiga), con un **componente Python
separado** para backtest histórico, calibración de los parámetros de esta
tabla, generación del dashboard y notificaciones, comunicándose con el EA vía
una base de datos SQLite compartida. El EA en MQL5 todavía no se ha escrito
(depende de Fase 0 completa + datos de bróker de la pregunta #1/#2) — este
repo por ahora contiene el motor de detección/backtest en Python.

## Calibración con datos reales (18-ago-2026)

Albert ha subido 4 de los documentos fuente. Incorporados en esta pasada:

- `Full_Backtest.numbers` — leído con `numbers-parser` (263 filas, columnas
  `Date, Trade, Day of Week, Order Type, Asian High/Low Sweep, Lot Size,
  Opening/Closing Time, Duration, SL, TP, RR, Close, G/L, Total,
  Percentage, Asian Range, 15m, 1H, 4H`). **Importante**: es un diario de
  resultados de operaciones (SL/TP/RR planeados, hora de entrada/salida,
  motivo de cierre, sesgo de estructura etiquetado a mano en 227 de 263
  filas) — **no** una serie de velas OHLC. Por tanto **no ha sido posible
  ejecutar `dax_model/detector.py` contra este archivo** para comprobar si
  el motor habría tomado las mismas 263 operaciones: eso requeriría el
  histórico real de velas de 5m/15m/1H/4H del DAX40 en ese periodo, que
  nadie ha aportado todavía. Lo que sí se ha hecho es usar las columnas del
  propio diario (SL, Close, 15m/1H/4H) para calibrar los parámetros
  numéricos de la tabla de arriba (fila 4bis) y para una comprobación propia
  de alineación 15m/1H (ver más abajo).
- `DAX40_Quantitative_Validation.pdf` (resumen ejecutivo, 15 páginas,
  preparado 18-ago-2026) y `Asian_Sweep_Paper.pdf` (el working paper
  completo del mismo estudio, v2, 176 páginas, mismo autor/dataset) —
  leídos íntegramente en su parte relevante (secciones 1–7 del resumen; 1–5
  del paper completo, que es donde está la comparación in/out-of-sample del
  15m vs 1H que resuelve la fila #11).
- `DAX40_Statistical_Review.pdf` — leído íntegro (7 páginas). Es un estudio
  **distinto**, con su propio dataset (n=225–261) y metodología, hecho por
  el propio Albert/su proceso — de ahí el desacuerdo con el working paper
  sobre el 1H (fila #11).

Pendientes de subir todavía: `DAX Trading Model.pdf`, `BE_Trades_Backtest.pages`,
`Morning Briefing *.md` (no bloqueante), y las 6 capturas del Apéndice A.

### Comprobación propia de alineación 15m/1H sobre `Full_Backtest.numbers`

Cálculo directo (no del paper, hecho aquí como sanity check) sobre las 227
filas etiquetadas, comparando la dirección de la operación (`Order Type`)
contra la etiqueta de estructura:

| Timeframe | Alineado (n, WR, PF) | En contra (n, WR, PF) |
|---|---|---|
| 15m | 134, 50.7%, PF 3.87 | 78, 32.1%, PF 1.33 |
| 1H | 129, 51.9%, PF 3.75 | 96, 36.5%, PF 1.81 |

Ambos muestran un efecto real en esta comprobación simple (no es un split
temporal riguroso como el del working paper). Esto no contradice la
decisión de la fila #11: el working paper específicamente prueba la
**estabilidad out-of-sample** del efecto (entrenar 2023-24, evaluar
2025-26) y ahí es donde el 1H pierde dos tercios de su magnitud mientras el
15m crece — un matiz que un split simple como el de arriba no captura.

El motor de detección (`dax_model/`) se construyó desde el principio para
ser agnóstico a la fuente de datos, con un punto de extensión ya listo para
`Full_Backtest.numbers` (`dax_model/backtest_loader.py`). **Los tests
unitarios siguen usando velas sintéticas diseñadas a mano**, no operaciones
reales — porque, como se explica arriba, no hay velas OHLC reales
disponibles todavía con las que construir un test de regresión honesto.
