# Arquitectura — CONFIRMADA por Albert

## Decisión

**VPS Windows + Expert Advisor nativo en MQL5** para la ejecución y gestión
de la operación en vivo (incluyendo el kill-switch de drawdown), acompañado
de un **componente Python separado** (mismo VPS o uno distinto) para:

- Ingesta/backtest de datos históricos.
- Calibración de los parámetros abiertos en `docs/OPEN_QUESTIONS.md`
  (filtro 15m ya fijado; precisión de entrada dentro del FVG, breakeven,
  etc. siguen pendientes de datos).
- Generación del dashboard en vivo.
- Notificaciones (pendiente de confirmar con Albert si se activan).

### Por qué este camino

El paquete oficial `MetaTrader5` de Python solo funciona sobre la terminal
MT5 nativa en Windows. Para ejecución 100% autónoma sobre una cuenta real
fondeada, el EA en MQL5 vive **dentro** del mismo proceso que ya gestiona la
conexión al bróker: la orden, su SL/TP en servidor, y el kill-switch de
drawdown siguen protegidos aunque cualquier proceso Python externo se caiga
o pierda conectividad. Esto es más robusto que depender de que *dos*
procesos (terminal MT5 + script Python) sigan vivos simultáneamente para que
una posición esté protegida — ver "Nota final" del brief original: prioridad
#2 es que el sistema falle de forma segura.

A cambio, el análisis HTF/backtesting/calibración estadística es más cómodo
en Python (este repo), y se traduce a MQL5 solo la lógica final ya calibrada
y congelada.

## Componentes

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  Componente Python (offline  │        │  EA MQL5 (Fase 1/2, en la     │
│  + calibración + dashboard)  │        │  terminal MT5, VPS Windows)   │
│                                │        │                                │
│  dax_model/  (este repo)      │  SQLite │  - lee niveles/parámetros      │
│   - detección de setups       │ ───────▶│    calibrados desde la BD      │
│   - motor de riesgo/guardrails│  (local │  - ejecuta MSS/FVG/entrada/SL  │
│   - backtest_loader           │  file)  │    en 5m directamente en MT5   │
│   - dashboard (Fase 1)        │◀─────── │  - kill-switch de drawdown     │
│   - notificaciones (Fase 1)   │  logs   │    (vive en el EA, no depende  │
│                                │  de     │    de Python)                  │
│                                │  trades │  - SL/TP puestos en servidor   │
└─────────────────────────────┘        └──────────────────────────────┘
```

- **SQLite compartido** como interfaz entre los dos componentes: el EA
  escribe cada operación (entrada/salida real, motivo de cierre, R
  realizado) y el componente Python la lee para el dashboard y para
  recalibrar. El EA nunca depende de que Python esté vivo para proteger una
  posición — SL/TP siempre puestos en servidor (bróker), nunca solo en
  memoria (ver `RISK_GUARDRAILS.md`, circuit breaker de conectividad).
- El componente Python puede, opcionalmente, escribir parámetros calibrados
  (p. ej. umbrales revisados) a una tabla de configuración que el EA lee al
  arrancar cada sesión — nunca en caliente a media operación.

## Estado actual de este repositorio

Fase 0 únicamente: `dax_model/` implementa la detección de setups y el
motor de riesgo en Python, sobre datos históricos, para verificar la lógica
contra `Full Backtest.numbers` en cuanto esté disponible (`OPEN_QUESTIONS.md`).
**No existe todavía ningún EA MQL5 ni conexión a MT4/5** — eso es Fase 1,
condicionado a:

1. Tener los datos de bróker/cuenta confirmados (preguntas #1–#3 de
   `OPEN_QUESTIONS.md`).
2. Que la lógica de `dax_model/` esté validada contra el histórico real.
3. Aprobación explícita de Albert para pasar de Fase 0 a Fase 1 (demo).

## Riesgos aceptados de esta arquitectura (a validar con Albert)

- Mantener dos bases de lógica (Python para calibración, MQL5 para
  ejecución) implica traducir manualmente la lógica final — riesgo de
  divergencia si se recalibra en Python y no se refleja en el EA. Mitigar
  con: la especificación mecánica (`STRATEGY_SPEC.md`) como fuente de verdad
  única, y tests equivalentes en ambos lados antes de cualquier despliegue.
- El EA en MQL5 no tiene acceso nativo cómodo a los datos de calibración de
  15m/HTF más allá de lo que la propia terminal MT5 le da vía `iBars`/
  `CopyRates` — hay que confirmar que el bróker de Albert ofrece histórico
  intradía suficiente en la terminal (ver Sección 6 del brief original).
