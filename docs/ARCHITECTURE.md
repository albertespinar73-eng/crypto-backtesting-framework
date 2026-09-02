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

`dax_model/` implementa la detección de setups y el motor de riesgo en
Python. Además, ya existe un **primer borrador** del EA en
`mql5/DAX40_AsianSweep_EA.mq5` (puerto directo de `dax_model/`, mismo
alcance: solo Modelo Primario), pero **sin compilar ni probar** — este
entorno no tiene MetaEditor/compilador MQL5. Esto NO es todavía "Fase 1
desplegada": es código listo para que Albert lo compile y lo corra en el
Probador de Estrategias de MT5 (ver `mql5/README.md`), sin conexión a
ninguna cuenta real ni demo. Sigue condicionado a:

1. Compilar el EA y corregir cualquier error de compilación (reportarlo de
   vuelta para arreglarlo).
2. Tener los datos de bróker/cuenta confirmados (preguntas #1–#3 de
   `OPEN_QUESTIONS.md`) — el offset de zona horaria y el valor del punto
   son inputs del EA, pero sus valores por defecto son placeholders.
3. Backtestear el EA en MT5 y comparar el orden de magnitud contra los
   resultados documentados en `docs/OPEN_QUESTIONS.md`/`RISK_GUARDRAILS.md`.
4. Aprobación explícita de Albert para pasar a Fase 1 (demo real contra
   MT4/5, no solo el Probador de Estrategias offline).

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
