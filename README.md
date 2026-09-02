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

## ¿Listo para copiar al EA de MT5?

**No.** Tres motivos concretos, no una cautela genérica:

1. **Es Python, el EA es MQL5.** No hay ninguna traducción automática; la
   lógica de `dax_model/` habría que reescribirla en MQL5 siguiendo
   `docs/ARCHITECTURE.md` — todavía no se ha escrito ni una línea de EA.
2. **No se ha podido verificar contra precio real.** `Full_Backtest.numbers`
   es un diario de resultados (SL/TP/RR planeados, hora, motivo de cierre),
   no una serie de velas OHLC — así que no ha sido posible comprobar que
   `dax_model/detector.py` habría detectado sweeps/MSS/FVG de forma
   equivalente a como se tomaron las 263 operaciones reales. Eso requiere
   el histórico real de velas de 5m/15m/1H/4H del DAX40, que todavía no se
   ha aportado.
3. **Solo el Modelo Primario está implementado.** Los modelos Alternativo
   (liquidez interna) y de Continuación siguen sin construir (ver
   `dax_model/detector.py`, cabecera del módulo).

Los nuevos filtros togglables (1H, SMA100) están **desactivados por
defecto** precisamente porque son territorio nuevo o en disputa entre los
propios informes de validación (ver `docs/OPEN_QUESTIONS.md` #11 y #12) —
pensados para que Albert los compare en backtest, no para ir a producción
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
db/schema.sql              Esquema SQLite para logging/dashboard (Fase 1+)
```

## Cómo correr los tests

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests -q
```

## Próximos pasos (no iniciados)

1. Conseguir histórico real de velas OHLC (5m/15m/1H/4H) del DAX40 para
   poder verificar `dax_model/detector.py` contra las 263 operaciones
   reales — `Full_Backtest.numbers` por sí solo no basta (ver arriba).
2. Resolver con Albert las preguntas #1–#3 y #13 de `docs/OPEN_QUESTIONS.md`
   (hora de apertura nocturna, bróker/valor del punto, reglas exactas de
   drawdown de la prop firm, si se implementa el hallazgo de los viernes).
3. Implementar los modelos Alternativo y de Continuación (Sección 2) sobre
   los mismos primitivos, una vez calibrada la definición de "liquidez
   interna".
4. Backtestear los toggles nuevos (1H, SMA100) con datos reales antes de
   decidir si alguno pasa a activado por defecto.
5. Escribir el EA en MQL5 (Fase 1) siguiendo `docs/ARCHITECTURE.md`, y
   desplegarlo en demo — nunca contra la cuenta real sin aprobación
   explícita de Albert.
