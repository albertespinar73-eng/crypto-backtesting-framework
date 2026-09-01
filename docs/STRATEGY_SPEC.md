# DAX40 Asian-Sweep — especificación mecánica

Traducción de las reglas del "DAX Trading Model" (más los refinamientos
cuantitativos ya validados) a una especificación objetiva, pensada para ser
implementada 1:1 en código. Cualquier ambigüedad restante está marcada
explícitamente y remitida a `docs/OPEN_QUESTIONS.md` — no se ha inventado
ningún umbral (ATR, ADX, "limpieza") que no esté en el texto original.

## Instrumento y timeframes

- DAX40 (Germany 40) CFD vía MT4/5. Solo intradía, sin overnight.
- Ejecución en 5 minutos. HTF: 4H y 1H (contexto, no bloqueante), 15m
  (filtro validado, ver más abajo).

## Killzone

- Única ventana de entrada: **08:15–10:45 CET**. Ninguna operación nueva
  fuera de esa ventana.
- El sweep y el impulso de vuelta pueden formarse antes de 08:15 (el sistema
  monitoriza desde el cierre del rango asiático), pero la decisión de si un
  setup completado antes de 08:15 sigue siendo válido al abrir la killzone
  es la pregunta abierta #5 — ver `OPEN_QUESTIONS.md`.

## Rango asiático

- Medido desde la apertura nocturna del CFD (hora por confirmar, pregunta
  abierta #1) hasta las 06:00 CET.
- `asian_high`, `asian_low`, `asian_equilibrium = (high + low) / 2`.

## Modelos de entrada

### 1. Primario — Asian Liquidity Sweep

1. Precio barre `asian_high` (para short) o `asian_low` (para long).
2. Displacement fuerte en dirección opuesta (ver "Detección de impulso").
3. **MSS (Market Structure Shift)** confirmado en 5m:
   - Short: una vela de 5m **cierra** (cuerpo, no mecha) por debajo del
     último Higher Low (HL) previo al sweep.
   - Long: simétrico — cierre por encima del último Lower High (LH) previo
     al sweep.
4. Uno o más FVGs de 5m se forman durante ese displacement (hueco de 3
   velas: sin solape entre el rango de la vela 1 y el de la vela 3).
5. Entrada y SL: ver "Entrada y stop loss".

### 2. Alternativo — sin barrido de liquidez asiática

- Se permite si el sesgo direccional es claro pero no se ha tomado
  `asian_high`/`asian_low`: barrido de liquidez interna (mínimos internos
  bajo el equilibrium asiático para largos; máximos internos sobre el
  equilibrium para cortos).
- Misma secuencia posterior: displacement → MSS por cierre → misma lógica
  de entrada/SL.

### 3. Continuación (A+)

- Tras el MSS inicial, un segundo Break of Structure (BoS) en la misma
  dirección deja un nuevo FVG. Entrada en ese FVG con la misma lógica de
  prioridad.

## Detección de impulso (displacement)

Definición objetiva (sin proxies adicionales de ATR/ADX/solape): el
displacement es el tramo de velas de 5m **desde la vela que barre la
liquidez (inclusive) hasta la vela que confirma el MSS por cierre
(inclusive)**. Los FVGs formados dentro de ese tramo, en orden cronológico,
son "primer FVG", "siguiente FVG", etc.

## Entrada y stop loss

Prioridad estricta, sin excepciones:

1. `origin` = nivel de liquidez barrido = origen del expansion leg (el
   último Higher High para un short / Lower Low para un long).
   `stop_loss = origin` siempre.
2. Para el primer FVG del tramo de displacement (cronológicamente más
   cercano al precio en el momento del sweep): calcula el borde del FVG
   **más cercano a `origin`** (el punto físicamente más profundo posible
   dentro del hueco, hacia Premium en un short / Discount en un long).
   - Si `distancia(origin, borde_cercano) <= max_sl_points` (~70 pts):
     entrada = ese borde. **No** se usa un punto fijo como "el 0.5" — el
     0.50–0.62 del PDF original es solo referencia aproximada, no fórmula.
   - Si no, ese FVG queda descartado.
3. Si el primer FVG no sirve, repite el paso 2 con el siguiente FVG
   formado en el mismo tramo (más cercano al origen, por tanto con menor
   distancia potencial al SL).
4. Si ningún FVG disponible permite `distancia(origin, entrada) <=
   max_sl_points`, **se descarta la operación por completo**. Nunca se
   ensancha el stop.
5. Si el FVG elegido ya fue mitigado (precio lo rellenó) antes de que la
   entrada se ejecute dentro de la killzone, se pasa directamente al
   siguiente FVG según la misma prioridad.

La precisión exacta de "el borde más cercano al origen" (frente a, por
ejemplo, la apertura de la vela de displacement más grande) es la pregunta
abierta #4 — implementado como parámetro de `EntryPolicy`, calibrable contra
`Full Backtest.numbers` en cuanto esté disponible.

## Objetivos

- TP por defecto: RR 1:2.
- Extensión permitida solo si hay liquidez clara más allá de 2R:
  `asian_high`/`asian_low`, PDH/PDL, high/low de la sesión NY anterior, o
  liquidez/ineficiencia de HTF.

## Breakeven

Regla base del PDF (ver pregunta abierta #7 para la versión revisada):
mover el SL a breakeven **solo si** el trade está por encima de 1R **y**
se confirma un BoS de 5m por cierre de vela más allá del último high/low
relevante. Nunca de forma anticipada.

## Filtro de 15 minutos (validado cuantitativamente)

Antes de tomar cualquier operación, calcular la última secuencia BoS/CHoCH
en 15m:

- Alineado con la dirección del setup → tomar con sizing normal.
- En contra → política configurable (`skip` por defecto, ver pregunta
  abierta #6; `reduce` como alternativa).

Los filtros de 1H y 4H **no se implementan como filtro de entrada** (no
replican / cambian de signo en el estudio out-of-sample). 4H/1H se muestran
en el dashboard como contexto informativo únicamente.

## Filtros explícitamente eliminados — NO implementar

- Bloqueo por noticias de alto impacto (CPI, NFP, FOMC, ECB).
- Filtro/reducción de riesgo por rango del día anterior (>400 pts).

## Gestión de riesgo (ver también `RISK_GUARDRAILS.md`)

- Riesgo fijo: 1% del equity por operación, siempre.
- Máximo 2 operaciones/día; parar tras la primera pérdida del día.
- `position_size = (equity * 0.01) / (stop_distance_points * point_value)`.
