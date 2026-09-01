-- Esquema SQLite para el registro de operaciones y setups (Sección 7 y 9 del
-- brief original). Pensado para que el futuro EA MQL5 (Fase 1/2) y el
-- componente Python (dashboard, calibración) lean/escriban la misma base.
--
-- Nada de esto se ha desplegado todavía: este repo está en Fase 0
-- (backtest/calibración offline, ver docs/DEPLOYMENT_PLAN.md). El esquema
-- se entrega ahora para que el dashboard y el logging de Fase 1 tengan un
-- contrato claro desde el principio.

PRAGMA foreign_keys = ON;

-- Una fila por cada setup EVALUADO por el detector, se haya tomado o no.
-- Es la fuente de verdad para "setups detectados hoy (tomados y
-- descartados, con motivo)" del dashboard.
CREATE TABLE IF NOT EXISTS setups (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date        TEXT NOT NULL,               -- fecha CET de la sesión (YYYY-MM-DD)
    model               TEXT NOT NULL CHECK (model IN ('primary_sweep', 'alternative_internal', 'continuation')),
    direction           TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    sweep_timestamp     TEXT NOT NULL,                -- ISO8601 UTC
    sweep_price         REAL NOT NULL,
    mss_timestamp        TEXT,                         -- NULL si nunca confirmó MSS
    mss_close            REAL,
    fvg_rank            INTEGER,                      -- 0 = primer FVG, 1 = siguiente, ... NULL si descartado antes de llegar aquí
    fvg_top             REAL,
    fvg_bottom          REAL,
    entry_price_planned REAL,
    stop_loss_planned   REAL,
    stop_distance_points REAL,
    take_profit_planned REAL,
    m15_aligned         INTEGER,                      -- 0/1/NULL (booleano; NULL = no se pudo evaluar)
    taken               INTEGER NOT NULL DEFAULT 0,   -- 0/1
    discard_reason_code TEXT,                          -- p.ej. SL_EXCEEDS_MAX, OUTSIDE_KILLZONE, M15_MISALIGNED, NO_FVG, ALL_FVG_MITIGATED, NO_REFERENCE_SWING
    discard_reason_detail TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_setups_session_date ON setups (session_date);
CREATE INDEX IF NOT EXISTS idx_setups_taken ON setups (taken);

-- Una fila por cada operación REALMENTE ejecutada (taken = 1 en `setups`).
-- Guarda fills reales, no teóricos (ver Sección 7 del brief: el histórico
-- manual usa fills idealizados; este esquema fuerza a distinguir planned vs real).
CREATE TABLE IF NOT EXISTS trades (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id              INTEGER NOT NULL REFERENCES setups (id),
    broker_ticket         TEXT,                        -- id de la orden en MT4/5, cuando aplique
    entry_timestamp       TEXT NOT NULL,
    entry_price_real      REAL NOT NULL,                -- fill real
    stop_loss_initial     REAL NOT NULL,
    take_profit_initial   REAL NOT NULL,
    position_size_lots    REAL NOT NULL,
    risk_amount_account_ccy REAL NOT NULL,
    moved_to_breakeven    INTEGER NOT NULL DEFAULT 0,
    breakeven_timestamp   TEXT,
    exit_timestamp        TEXT,
    exit_price_real       REAL,
    close_reason          TEXT CHECK (close_reason IN ('take_profit', 'stop_loss', 'breakeven', 'manual_close', 'kill_switch', NULL)),
    r_multiple_realized   REAL,
    cost_points           REAL,                         -- spread + slippage realmente sufrido (Sección 3: el edge sobrevive hasta ~26pts de coste)
    filters_passed        TEXT,                          -- JSON: {"m15_aligned": true, ...}
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_setup_id ON trades (setup_id);
CREATE INDEX IF NOT EXISTS idx_trades_entry_timestamp ON trades (entry_timestamp);

-- Contadores diarios (Sección 5 guardrails: máx 2 operaciones/día, parar
-- tras la primera pérdida). Una fila por día natural CET.
CREATE TABLE IF NOT EXISTS daily_counters (
    session_date      TEXT PRIMARY KEY,
    trades_taken      INTEGER NOT NULL DEFAULT 0,
    stopped_for_day   INTEGER NOT NULL DEFAULT 0,
    day_start_equity  REAL,
    day_end_equity    REAL
);

-- Snapshots de drawdown para el kill-switch de cuenta prop/fondeada y para
-- la barra de proximidad al kill-switch del dashboard.
CREATE TABLE IF NOT EXISTS drawdown_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    equity             REAL NOT NULL,
    day_start_equity   REAL NOT NULL,
    account_start_equity REAL NOT NULL,
    daily_drawdown_pct REAL NOT NULL,
    total_drawdown_pct REAL NOT NULL,
    state              TEXT NOT NULL CHECK (state IN ('active', 'warning', 'halted'))
);

CREATE INDEX IF NOT EXISTS idx_drawdown_timestamp ON drawdown_snapshots (timestamp);

-- Eventos de sistema: desconexiones, errores no controlados, kill-switches
-- disparados — para la alerta mínima recomendada en la Sección 7 del brief
-- (pregunta abierta #9: canal de notificación todavía por confirmar).
CREATE TABLE IF NOT EXISTS system_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    severity    TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    event_type  TEXT NOT NULL,   -- p.ej. 'mt5_disconnected', 'kill_switch_halted', 'unhandled_error'
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS idx_system_events_severity ON system_events (severity);
