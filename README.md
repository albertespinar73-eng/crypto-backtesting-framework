# DAX40 Asian-Sweep — sistema de trading automático (Fase 0)

Automatización del "DAX Trading Model" de Albert para DAX40 (Germany 40)
vía MT4/5: barrido de liquidez asiática, MSS por cierre de vela, entrada en
FVG con prioridad y stop máximo ~70 puntos, filtro de estructura de 15
minutos, y guardrails de riesgo duros (1% por operación, máx 2 trades/día,
kill-switch de drawdown). Ver la especificación completa en
[`docs/STRATEGY_SPEC.md`](docs/STRATEGY_SPEC.md).

## Estado actual: Fase 0 (backtest/calibración offline)

**No hay ninguna conexión a MT4/5, ninguna cuenta demo ni real configurada,
y no se ha ejecutado ninguna operación real o simulada contra datos de
mercado reales.** Este repositorio contiene únicamente:

- La especificación mecánica de la estrategia, traducida 1:1 desde el brief
  original ([`docs/STRATEGY_SPEC.md`](docs/STRATEGY_SPEC.md)).
- El motor de detección de setups en Python (`dax_model/`), con tests sobre
  velas sintéticas — **no** sobre operaciones reales, porque `Full Backtest.numbers`
  todavía no está disponible en este repo (ver más abajo).
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

Todas las decisiones y parámetros que dependen de datos que Albert todavía
no ha subido (`Full Backtest.numbers`, `DAX Trading Model.pdf`,
`DAX40_Quantitative_Validation.pdf`, `BE_Trades_Backtest.pages`, las 6
capturas del Apéndice A) están documentadas como pendientes en
[`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md), junto con el valor por
defecto que usa el código mientras tanto y dónde vive ese parámetro.

## Estructura del repo

```
docs/
  STRATEGY_SPEC.md       Especificación mecánica de la estrategia
  ARCHITECTURE.md         Arquitectura de ejecución (confirmada)
  RISK_GUARDRAILS.md       Guardrails de riesgo como código
  DEPLOYMENT_PLAN.md       Plan de despliegue por fases
  OPEN_QUESTIONS.md        Preguntas abiertas / parámetros pendientes de calibrar
dax_model/                Motor de detección de setups y riesgo (Python)
  models.py                Estructuras de datos (Candle, FVG, Setup, ...)
  sessions.py               Rango asiático + killzone
  structure.py               Swing points (HH/HL/LH/LL) + MSS por cierre
  fvg.py                      Fair Value Gaps + mitigación
  entry.py                     Prioridad de entrada/SL
  htf_filter.py                 Filtro de alineación de 15m
  be_rule.py                     Regla de breakeven (base del PDF)
  risk.py                         Sizing + límites diarios + kill-switch de drawdown
  detector.py                      Orquestador del Modelo Primario
  backtest_loader.py                Loader de Full Backtest.numbers (pendiente del archivo)
tests/                     Tests unitarios sobre velas sintéticas
pine/                      Indicador Pine Script v5 (verificación visual)
db/schema.sql              Esquema SQLite para logging/dashboard (Fase 1+)
```

## Cómo correr los tests

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests -q
```

## Próximos pasos (no iniciados)

1. Recibir de Albert los documentos fuente y calibrar contra
   `Full Backtest.numbers` los parámetros marcados como pendientes en
   `docs/OPEN_QUESTIONS.md` (precisión exacta de entrada en el FVG, regla de
   breakeven definitiva, hora de apertura nocturna real, valor del punto,
   reglas de drawdown de la prop firm).
2. Verificar `dax_model/detector.py` contra las 263 operaciones reales.
3. Implementar los modelos Alternativo y de Continuación (Sección 2) sobre
   los mismos primitivos, una vez calibrada la definición de "liquidez
   interna".
4. Escribir el EA en MQL5 (Fase 1) siguiendo `docs/ARCHITECTURE.md`, y
   desplegarlo en demo — nunca contra la cuenta real sin aprobación
   explícita de Albert.
