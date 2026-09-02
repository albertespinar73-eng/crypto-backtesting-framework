# DAX40 Asian-Sweep — sistema de trading automático (Fase 0)

Automatización del "DAX Trading Model" de Albert para DAX40 (Germany 40)
vía MT4/5: barrido de liquidez asiática, MSS por cierre de vela, entrada en
FVG con prioridad y stop máximo calibrado a 75 puntos, filtro de estructura
de 15m (más 1H y SMA100 opcionales, togglables para A/B backtest), y
guardrails de riesgo duros (1% por operación, máx 2 trades/día, kill-switch
de drawdown). Ver la especificación completa en
[`docs/STRATEGY_SPEC.md`](docs/STRATEGY_SPEC.md).

## Estado actual: Fase 0 (backtest/calibración offline)

**No hay ninguna conexión a MT4/5, ninguna cuenta demo ni real configurada,
y no se ha ejecutado ninguna operación real o simulada contra datos de
mercado reales.** El código Python de este repositorio **no está listo para
traducirse al EA de MT5 todavía** — ver "¿Listo para el EA?" más abajo.

Este repositorio contiene:

- La especificación mecánica de la estrategia, traducida 1:1 desde el brief
  original ([`docs/STRATEGY_SPEC.md`](docs/STRATEGY_SPEC.md)), con los
  umbrales numéricos ya calibrados contra `Full_Backtest.numbers` donde ha
  sido posible.
- El motor de detección de setups en Python (`dax_model/`), con filtros de
  estructura (15m activo, 1H y SMA100 opcionales) togglables para backtest
  A/B, y tests sobre velas sintéticas.
- La propuesta de arquitectura para Fase 1/2, ya confirmada por Albert
  ([`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)): VPS Windows + EA en MQL5
  para ejecución/kill-switch, componente Python separado para
  calibración/dashboard.
- Los guardrails de riesgo formalizados ([`docs/RISK_GUARDRAILS.md`](docs/RISK_GUARDRAILS.md)).
- El plan de despliegue por fases ([`docs/DEPLOYMENT_PLAN.md`](docs/DEPLOYMENT_PLAN.md)).
- Un indicador Pine Script v5 propio para verificación visual en TradingView
  ([`pine/dax_asian_sweep_mss.pine`](pine/dax_asian_sweep_mss.pine)).
- El esquema SQLite para logging de operaciones y el futuro dashboard
  ([`db/schema.sql`](db/schema.sql)).

Todas las decisiones y parámetros, calibrados o todavía pendientes, están en
[`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) — incluyendo qué se ha
podido calibrar ya con los documentos que Albert ha subido
(`Full_Backtest.numbers`, `DAX40_Quantitative_Validation.pdf`,
`Asian_Sweep_Paper.pdf`, `DAX40_Statistical_Review.pdf`) y qué sigue
pendiente de datos de bróker/cuenta que solo él tiene.

## ¿Listo para backtestear/copiar al EA de MT5?

**Hay un primer borrador para backtest, pero no está listo para real ni
demo.** Ver [`mql5/DAX40_AsianSweep_EA.mq5`](mql5/DAX40_AsianSweep_EA.mq5) y
las instrucciones paso a paso en [`mql5/README.md`](mql5/README.md). Tres
matices importantes:

1. **Sin compilar.** Este entorno no tiene MetaEditor/compilador MQL5 — el
   archivo se ha escrito con cuidado (mismo diseño y lógica que
   `dax_model/`, comprobado a mano) pero necesita compilarse (F7) y
   probarse en MT5 antes de fiarse de él. Si da errores de compilación,
   repórtalos para corregirlos.
2. **No se ha podido verificar contra precio real todavía.**
   `Full_Backtest.numbers` es un diario de resultados (SL/TP/RR planeados,
   hora, motivo de cierre), no una serie de velas OHLC — así que ni el EA
   ni `dax_model/detector.py` se han podido comparar operación a operación
   contra las 263 reales. Para eso hace falta el histórico real de velas
   de 5m/15m/1H/4H del DAX40, que el Probador de Estrategias de MT5 sí
   puede darte directamente (ver `mql5/README.md`).
3. **Solo el Modelo Primario está implementado**, en ambos lados (Python y
   MQL5). Los modelos Alternativo (liquidez interna) y de Continuación
   siguen sin construir.

Los nuevos filtros togglables (1H, SMA100) están **desactivados por
defecto** en ambos lados, precisamente porque son territorio nuevo o en
disputa entre los propios informes de validación (ver
`docs/OPEN_QUESTIONS.md` #11 y #12) — pensados para que Albert los compare
en backtest (el Probador de Estrategias de MT5 puede optimizar estos
toggles automáticamente, ver `mql5/README.md` §5), no para ir a producción
tal cual.

## Estructura del repo

```
docs/
  STRATEGY_SPEC.md       Especificación mecánica de la estrategia
  ARCHITECTURE.md         Arquitectura de ejecución (confirmada)
  RISK_GUARDRAILS.md       Guardrails de riesgo como código
  DEPLOYMENT_PLAN.md       Plan de despliegue por fases
  OPEN_QUESTIONS.md        Preguntas abiertas / parámetros calibrados o pendientes
dax_model/                Motor de detección de setups y riesgo (Python)
  models.py                Estructuras de datos (Candle, FVG, Setup, ...)
  sessions.py               Rango asiático + killzone
  structure.py               Swing points (HH/HL/LH/LL) + MSS por cierre
  fvg.py                      Fair Value Gaps + mitigación
  entry.py                     Prioridad de entrada/SL (cap calibrado a 75pts)
  htf_filter.py                 Filtro de alineación 15m / 1H (togglable)
  trend_filter.py                 Filtro de tendencia SMA100 (togglable, sin validar)
  be_rule.py                       Regla de breakeven (base del PDF)
  risk.py                           Sizing + límites diarios + kill-switch de drawdown
  detector.py                        Orquestador del Modelo Primario
  backtest_loader.py                  Loader de Full_Backtest.numbers
tests/                     Tests unitarios sobre velas sintéticas
pine/                      Indicador Pine Script v5 (verificación visual)
mql5/                      EA MQL5 para backtest en MT5 (borrador, sin compilar)
  DAX40_AsianSweep_EA.mq5   Puerto directo de dax_model/, mismo alcance (solo Modelo Primario)
  README.md                  Pasos para instalar, compilar y backtestear en el Probador de Estrategias
db/schema.sql              Esquema SQLite para logging/dashboard (Fase 1+)
```

## Cómo correr los tests

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests -q
```

## Próximos pasos

1. Compilar `mql5/DAX40_AsianSweep_EA.mq5` en MetaEditor y corregir
   cualquier error de compilación (reportarlo de vuelta).
2. Backtestear en el Probador de Estrategias de MT5 siguiendo
   `mql5/README.md` — esto también resuelve el punto anterior de "conseguir
   histórico real de velas OHLC", porque el propio MT5 lo provee.
3. Resolver con Albert las preguntas #1–#3 y #13 de `docs/OPEN_QUESTIONS.md`
   (hora de apertura nocturna, bróker/valor del punto, reglas exactas de
   drawdown de la prop firm, si se implementa el hallazgo de los viernes).
4. Implementar los modelos Alternativo y de Continuación (Sección 2) sobre
   los mismos primitivos, una vez calibrada la definición de "liquidez
   interna" — en Python y en el EA.
5. Backtestear los toggles nuevos (1H, SMA100) con datos reales antes de
   decidir si alguno pasa a activado por defecto.
6. Desplegar en demo (Fase 1) siguiendo `docs/DEPLOYMENT_PLAN.md` — nunca
   contra la cuenta real sin aprobación explícita de Albert.
