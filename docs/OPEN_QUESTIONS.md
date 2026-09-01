# Preguntas abiertas para Albert

Este documento consolida todas las decisiones que el propio prompt de
especificación marca como pendientes de confirmación por Albert antes de
tocar la cuenta real (y, en varios casos, antes de fijar el comportamiento
por defecto en el código). Mientras no se confirmen, el código usa el
**valor por defecto** indicado, expuesto como parámetro configurable — nunca
hardcodeado sin posibilidad de cambio.

Estado: dos decisiones ya confirmadas por Albert (arquitectura y filtro 15m,
ver más abajo); el resto sigue pendiente. No se ha conectado nada a MT4/5 ni
a una cuenta real; esta fase (Fase 0) es solo backtest/calibración offline.

| # | Pregunta | Default actual en código | Dónde vive el parámetro |
|---|----------|---------------------------|--------------------------|
| 1 | Hora exacta de apertura de la sesión nocturna del DAX40 CFD en el bróker real de Albert (inicio del rango asiático; el fin, 06:00 CET, ya está fijado). | `23:00 CET` (placeholder, típico de FXCM/OANDA-style feeds) | `dax_model.sessions.AsianSessionConfig.open_time_cet` |
| 2 | Bróker MT4/5 concreto, tipo de cuenta, apalancamiento, valor exacto del punto/tick para el DAX40 CFD. | `point_value=1.0` (1 punto = 1 unidad de cuenta por lote estándar; **sin confirmar**) | `dax_model.risk.InstrumentSpec` |
| 3 | Nombre de la prop firm (o cuenta propia) y reglas exactas de drawdown diario/total y tamaño de cuenta. | Placeholder: DD diario 5%, DD total 10%, aviso al 80% del límite | `dax_model.risk.DrawdownGuardrail` |
| 4 | Precisión de la entrada dentro del FVG: ¿nivel de referencia concreto (p. ej. apertura de la vela de displacement más grande) o juicio visual "lo más profundo hacia Premium/Discount que el límite de 70 pts permita"? | Se implementa como **el borde del FVG más cercano al origen del leg** (el punto físicamente más profundo posible dentro del hueco), descartando el FVG si ese borde ya excede 70 pts. Ver `docs/STRATEGY_SPEC.md#entrada-y-stop-loss`. | `dax_model.entry.choose_entry` (parametrizable vía `EntryPolicy`) |
| 5 | ¿Un setup con MSS+FVG completado antes de las 08:15 CET sigue siendo válido para entrar en cuanto abre la killzone, o solo cuentan los setups completados dentro de 08:15–10:45? | Se toma **solo si el FVG de entrada sigue sin mitigar** al momento de evaluar y sigue siendo el primer/siguiente FVG válido según la lógica de prioridad. Configurable vía `allow_pre_killzone_setups`. | `dax_model.detector.DetectorConfig` |
| 6 | Filtro de 15 minutos en contra: ¿se descarta la operación del todo, o se toma con tamaño reducido? | **CONFIRMADO por Albert: descartar (`skip`)**, como en la simulación del estudio (PF 2.67→4.04, DD máx 5.0R→4.0R, -36% operaciones). | `dax_model.htf_filter.M15FilterPolicy` (`"skip"` \| `"reduce"`) |
| 7 | Regla de breakeven definitiva: la del PDF tal cual, o esperar al cierre del estudio `be_rule_study`. | Regla base del PDF: mover a BE solo si trade > 1R **y** hay BoS de 5m confirmado por cierre de vela más allá del último high/low relevante. | `dax_model.be_rule.BreakevenPolicy` |
| 8 | Duración mínima y criterios de salida de la fase demo antes de pasar a real. | Sin definir — **no hay fecha ni nº de operaciones asumido**. Ver `docs/DEPLOYMENT_PLAN.md`. | N/A (decisión de proceso, no de código) |
| 9 | ¿Notificaciones críticas (Telegram/email) para kill-switches/errores, aunque se pidiera "solo dashboard"? | Se recomienda sí como red de seguridad mínima; no implementado todavía (Fase 0 es offline). | Pendiente de diseño en Fase 1 |
| 10 | ¿Journaling también en Notion ("Trading Journal 2026") además de/en vez de SQLite local? | SQLite es la fuente de verdad; export a Notion sería un paso adicional opcional. | Pendiente de diseño en Fase 1 |

## Decisión de arquitectura (Sección 6) — CONFIRMADA

Ver `docs/ARCHITECTURE.md`. **Confirmado por Albert: VPS Windows + EA nativo
en MQL5 para ejecución/gestión de la orden y el kill-switch de drawdown**
(sobrevive aunque el proceso Python se caiga), con un **componente Python
separado** para backtest histórico, calibración de los parámetros de esta
tabla, generación del dashboard y notificaciones, comunicándose con el EA vía
una base de datos SQLite compartida. El EA en MQL5 todavía no se ha escrito
(depende de Fase 0 completa + datos de bróker de la pregunta #1/#2) — este
repo por ahora contiene el motor de detección/backtest en Python.

## Documentos fuente pendientes de entrega

Albert ha indicado que los subirá. Ninguno de los siguientes archivos está
presente en este repositorio todavía. Sin ellos, **no es posible completar
ni validar la Fase 0** (calibración cuantitativa contra operaciones reales):

- `DAX Trading Model.pdf`
- `Full Backtest.numbers` (263 operaciones, 2023-08-21 a 2026-08-18)
- `DAX40_Quantitative_Validation.pdf` / `Asian Sweep Paper.pdf`
- `BE_Trades_Backtest.pages`
- `Morning Briefing *.md` (formato de referencia, no bloqueante)
- Apéndice A: 6 capturas de TradingView (`01_liquidez_interna_2026-08-18.png` … `06_entrada_ajustada_SL60_2026-07-16.png`)

El motor de detección (`dax_model/`) se ha construido para ser agnóstico a la
fuente de datos, con puntos de extensión claros para conectar
`numbers-parser` en cuanto `Full Backtest.numbers` esté disponible (ver
`dax_model/backtest_loader.py`). **No se han inventado datos de operaciones
reales para "rellenar" esta ausencia** — los tests unitarios usan velas
sintéticas diseñadas a mano para ejercitar cada regla, no operaciones reales.
