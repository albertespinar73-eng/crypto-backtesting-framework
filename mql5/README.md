# DAX40_AsianSweep_EA — cómo backtestear en MT5

`DAX40_AsianSweep_EA.mq5` es el puerto a MQL5 del motor de detección de
`dax_model/` (Python), para poder correr el backtest directamente en el
Probador de Estrategias de MT5 en vez de solo en Python. Mismo alcance que
`dax_model/detector.py`: **solo el Modelo Primario**, TP fijo 1:2, sin
modelos Alternativo/Continuación todavía (ver cabecera del propio archivo).

**No se ha compilado ni probado todavía** — este entorno no tiene
MetaEditor/compilador MQL5. Cuando lo compiles, si `F7` da errores,
pégamelos y los corrijo.

## 1. Instalar

1. En MT5: `Archivo → Abrir carpeta de datos` → `MQL5\Experts\`.
2. Copia ahí `DAX40_AsianSweep_EA.mq5` (puedes crear una subcarpeta, p. ej.
   `MQL5\Experts\DAX40\`).
3. Abre el archivo en MetaEditor (F4 desde MT5, o doble clic desde el
   Navegador) y compílalo (F7). Revisa la pestaña "Errores".

## 2. Antes de la primera pasada — ajustar inputs críticos

Estos tres NO tienen un valor correcto por defecto porque dependen de tu
bróker/cuenta real (ver `docs/OPEN_QUESTIONS.md` #1–#3):

- **`InpBrokerToCETOffsetHours`**: horas a sumar a la hora del bróker para
  obtener CET. Si no lo ajustas, el rango asiático y la killzone se
  calculan mal. Compruébalo viendo a qué hora del bróker corresponde
  actualmente las 08:15 CET (o las 14:15 si estás en verano — MT5 no
  gestiona el cambio de hora automáticamente en este offset, es fijo; si
  el bróker no cambia de horario en el mismo momento que CET/CEST, puede
  hacer falta revisar el offset dos veces al año).
- **`InpPointValuePerLot`**: déjalo en `0` para que el EA lo calcule solo
  desde `SYMBOL_TRADE_TICK_VALUE`/`SYMBOL_TRADE_TICK_SIZE` del símbolo real
  de tu bróker (recomendado), o fíjalo a mano si sabes el valor exacto.
- El resto de inputs (SL máximo, riesgo, límites diarios, drawdown,
  filtros) ya vienen con los valores calibrados/confirmados documentados en
  `docs/OPEN_QUESTIONS.md` y `docs/RISK_GUARDRAILS.md` — no hace falta
  tocarlos para una primera pasada.

## 3. Configurar el Probador de Estrategias

`Ctrl+R` en MT5 →

- **Expert Advisor**: `DAX40_AsianSweep_EA`.
- **Símbolo**: el DAX40/GER40/DE40 real de tu bróker (el nombre exacto
  varía).
- **Periodo**: M5 (el EA usa `CopyRates` internamente para M5/M15/H1; el
  periodo del gráfico del tester solo marca cada cuánto se dispara
  `OnTick`).
- **Modelo**: *"Todos los ticks reales"* si tu bróker tiene histórico de
  ticks para el DAX40; si no, *"Todos los ticks"* (generado). Evita
  *"Solo precios de apertura"* — el MSS depende del cierre exacto de cada
  vela de 5m y ese modelo no lo simula con fidelidad.
- **Rango de fechas**: todo el histórico que tu bróker tenga disponible.
  Probablemente no llegue hasta 2023-08 (el inicio de
  `Full_Backtest.numbers`) — es normal, son datasets distintos y no pasa
  nada si el rango es más corto.
- **Depósito inicial / apalancamiento**: los de tu cuenta real (o los que
  quieras simular).

## 4. Primera pasada (baseline)

Corre una vez con los inputs de filtros en sus valores por defecto
(`InpM15FilterEnabled=true`, `InpH1FilterEnabled=false`,
`InpMATrendFilterEnabled=false`) — esto reproduce el comportamiento que
Albert ya confirmó. Anota profit factor, expectancy, drawdown máximo, nº de
operaciones.

## 5. Comparar los filtros con/sin (Optimización)

Pestaña **Optimización** del Probador de Estrategias:

1. Marca como "optimizar" estos tres inputs booleanos:
   `InpM15FilterEnabled`, `InpH1FilterEnabled`, `InpMATrendFilterEnabled`.
2. Rango de cada uno: `false` a `true`, paso 1 (booleano → 2 valores).
3. Esto genera automáticamente las 8 combinaciones con/sin cada filtro, sin
   tener que relanzar manualmente uno a uno.
4. Ordena los resultados por Profit Factor o por Drawdown relativo para ver
   qué combinación se comporta mejor — pero recuerda que **ninguno de los
   dos filtros nuevos (1H, SMA100) está validado con datos reales
   todavía**: si el backtest los favorece, es una señal a investigar más,
   no una confirmación automática (riesgo de sobreajuste con solo unas
   pocas combinaciones probadas — ver la sección de "Probability of
   Backtest Overfitting" en `Asian_Sweep_Paper.pdf` sobre por qué esto
   importa).

## 6. Modo visual (para verificar sweeps/MSS/FVG a ojo)

En la pestaña **Ajustes**, marca "Modo visual" y corre unas pocas sesiones.
Compara lo que hace el EA contra el indicador Pine Script
(`pine/dax_asian_sweep_mss.pine`) cargado en el gráfico equivalente de
TradingView para esas mismas fechas — es una comprobación cualitativa
rápida, no sustituye una validación estadística completa.

## 7. Qué NO hace todavía esta primera versión

- No implementa los modelos Alternativo (liquidez interna) ni de
  Continuación — solo Primario (barrido de Asian High/Low).
- El take-profit es siempre RR 1:2 fijo; no hay extensión hacia
  PDH/PDL/liquidez de HTF.
- El kill-switch de drawdown cierra posiciones y desactiva el EA
  (`ExpertRemove` no se llama automáticamente — lo verás en el log como
  "KILL-SWITCH" y tendrás que quitar el EA del gráfico a mano; esto es
  intencional para no perder el control manual del gráfico en real/demo).
- No hay notificaciones (Telegram/email) todavía — pregunta abierta #9.

No lo conectes a una cuenta real ni siquiera demo sin haber revisado
`docs/DEPLOYMENT_PLAN.md` primero.
