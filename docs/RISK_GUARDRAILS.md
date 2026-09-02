# Guardrails de riesgo — deben ser código, no configuración saltable

Estas comprobaciones son obligatorias e infranqueables. Cada vez que
bloquean una operación, se loguea el motivo (para el dashboard y para
`db/schema.sql`). Implementadas en `dax_model/risk.py` para Fase 0
(backtest); en Fase 1/2 la misma lógica se traduce al EA MQL5, que además
debe poder actuar aunque el componente Python esté caído (ver
`ARCHITECTURE.md`).

## 1. Riesgo por operación: siempre 1%

```
position_size = (equity * 0.01) / (stop_distance_points * point_value)
```

Sin excepciones, sin condicionar al rango del día anterior (ese filtro fue
eliminado explícitamente por Albert — no reintroducirlo).

## 2. SL máximo — CALIBRADO a 75 puntos (antes placeholder ~70)

Si `dax_model.entry.choose_entry` no encuentra ninguna combinación de FVG
(primero / siguiente) con `stop_distance <= max_sl_points`, la operación se
descarta. Este chequeo vive dentro de la propia función de entrada — no es
posible construir un `Trade` con un stop mayor al límite: `choose_entry`
devuelve `None` en ese caso y el detector no genera ninguna señal.

Calibrado contra las 263 operaciones reales de `Full_Backtest.numbers`: el
SL real va de 20 a 75 puntos (mediana 40, media 40.8; solo 1 operación por
encima de 70, ninguna por encima de 75). `DAX40_Statistical_Review.pdf`
confirma que el rango se ensanchó explícitamente de 20–60 a 20–75/25–75
puntos por el régimen de volatilidad de 2026 (rango diario medio ~390pt vs
~180–200pt en 2023–24) — una decisión de ajuste de régimen, no una
optimización de backtest (el propio informe encuentra que el tamaño del SL
no predice el resultado, p=0.27–0.66). Nuevo default:
`EntryPolicy.max_sl_points = 75.0` / `InstrumentSpec.max_stop_points = 75.0`.

## 3. Máximo 2 operaciones/día; parar tras la primera pérdida

- Contador diario reseteado a **medianoche CET** (recomendado por defecto;
  confirmar con Albert si prefiere el cierre de sesión en su lugar).
- Tras cualquier pérdida (trade cerrado con R < 0), no se generan más
  señales el resto del día natural, independientemente de si se llegó al
  máximo de 2 operaciones.
- Implementado en `dax_model.risk.DailyLimiter` como una máquina de estados
  explícita (`trades_today`, `stopped_for_day`), consultada obligatoriamente
  antes de emitir cualquier señal nueva.

## 4. Kill-switch de cuenta prop/fondeada

Placeholder de partida (pregunta abierta #3 — cifras exactas por confirmar):

- Drawdown diario máximo: 5% del equity de inicio de día.
- Drawdown total máximo: 10% del equity inicial de la cuenta.
- Al 80% de cualquiera de los dos límites: dejar de abrir operaciones
  nuevas + log crítico.
- Al 100%: cerrar posiciones abiertas + desactivación completa hasta
  reactivación manual.

Implementado en `dax_model.risk.DrawdownGuardrail`. En Fase 1/2, esta misma
lógica debe vivir **también** dentro del EA MQL5 (no solo en el componente
Python) — es la pieza más crítica de "fallar de forma segura" del brief
original, así que no puede depender de que un proceso externo esté vivo.

**Dato de contexto real** (no cambia el placeholder, pero lo informa):
`Asian_Sweep_Paper.pdf` simula 20.000 resamples de las 263 operaciones
reales a 1% de riesgo fijo. El drawdown máximo histórico real fue 5.0R; en
simulación, el drawdown mediano de un run de este tamaño es 6.2R, el
percentil 95 es 10.0R, y la probabilidad de tocar un 10% de drawdown de
cuenta en algún punto de un run de 263 operaciones es **7.2%** (5.8% usando
solo el periodo out-of-sample 2025-26). Si el límite real de la prop firm
(pregunta abierta #3) resulta ser 10% total a 1% de riesgo por operación,
esto sugiere que el margen de seguridad no es enorme — información a tener
en cuenta al fijar el `warning_threshold_pct` real, no una razón para
cambiar el placeholder por mi cuenta.

## 5. Circuit breaker de conectividad

Fase 1/2 (no aplica a backtest offline): política explícita pendiente de
implementar en el EA —

- SL/TP siempre puestos **en servidor** (bróker) en el momento de abrir la
  posición, nunca solo gestionados en memoria por el bot.
- Si el EA pierde conexión con el bróker mientras hay una posición abierta:
  loguear la desconexión y alertar (canal de alertas: pregunta abierta #9);
  la posición sigue protegida por el SL/TP ya puesto en servidor
  independientemente de si el EA/terminal se recupera a tiempo.

## Trazabilidad

Cada vez que un guardrail bloquea una operación (SL > 70pts, límite diario
alcanzado, drawdown en zona de aviso/kill), se registra con motivo explícito
— ver columnas `blocked_reason` / `filters_passed` en `db/schema.sql` y la
sección "Setups descartados" del dashboard (Sección 9 del brief original).
