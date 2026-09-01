# Plan de despliegue

## Fase 0 — Backtest/calibración offline (repo actual)

- Implementar la detección de setups (`docs/STRATEGY_SPEC.md`) en Python:
  hecho para la lógica mecánica (`dax_model/`), pendiente de verificar
  contra `Full Backtest.numbers` en cuanto Albert lo suba.
- Verificar la detección de displacement/FVG contra ejemplos reales
  (Apéndice A del brief original — pendiente de recibir las 6 imágenes).
- Comparar contra `Full Backtest.numbers` para confirmar que el sistema
  habría tomado operaciones razonablemente parecidas a las reales.
- Entregable adicional: indicador Pine Script propio (MSS por cierre de
  vela, Asian range, FVGs) para verificación visual en TradingView durante
  la fase de demo — ver `pine/dax_asian_sweep_mss.pine`.
- **Salida de Fase 0**: lógica de `dax_model/` validada contra el histórico
  real + parámetros abiertos (`OPEN_QUESTIONS.md` #4, #7) calibrados con
  datos reales, no con supuestos.

## Fase 1 — Demo/paper en vivo

- Desplegar el sistema completo (incluyendo guardrails y kill-switches)
  contra una cuenta demo de MT5, mismo bróker/spread/slippage esperado que
  la cuenta real.
- **Duración**: sin definir todavía — pregunta abierta #8. No arrancar con
  una cifra asumida; acordarla explícitamente con Albert antes de fijar
  fecha de salida a real.
- **Criterios de salida demo → real** (a proponer y que Albert apruebe, no a
  fijar unilateralmente):
  - Nº mínimo de operaciones en demo (propuesta de partida a discutir: que
    cubra al menos varias semanas de la killzone real, no un número
    arbitrario).
  - Cero errores críticos/desconexiones no gestionadas durante el periodo.
  - Kill-switch de drawdown verificado con al menos un test forzado
    (simular llegar al 80% y al 100% del límite y confirmar que el sistema
    reacciona como en `RISK_GUARDRAILS.md`).
  - Expectancy/drawdown en demo dentro de un rango razonable respecto al
    histórico validado en Fase 0 (a definir el rango exacto con Albert).

## Fase 2 — Real

- Activar contra la cuenta real fondeada **solo** tras aprobación explícita
  de Albert.
- Kill-switch de drawdown de la prop firm activo desde el primer minuto,
  con las cifras reales confirmadas (no el placeholder 5%/10%).

## Estado actual

Este repositorio está en **Fase 0**, y dentro de Fase 0 todavía a la espera
de los documentos fuente (`OPEN_QUESTIONS.md`). No hay ninguna conexión a
MT4/5, ni cuenta demo ni real configurada.
