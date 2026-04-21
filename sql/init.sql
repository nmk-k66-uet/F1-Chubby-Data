-- F1-Chubby-Data: PostgreSQL Schema
-- Serves: calendar, session results, driver/constructor standings

-- ==========================================
-- RACE CALENDAR
-- ==========================================
CREATE TABLE IF NOT EXISTS race_calendar (
    year        INT         NOT NULL,
    round       INT         NOT NULL,
    event_name  TEXT        NOT NULL,
    country     TEXT        NOT NULL,
    event_date  DATE,
    circuit     TEXT,
    event_format TEXT       DEFAULT 'conventional',
    PRIMARY KEY (year, round)
);

CREATE INDEX IF NOT EXISTS idx_calendar_year ON race_calendar (year);

-- ==========================================
-- SESSION RESULTS (Race, Qualifying, Sprint)
-- ==========================================
CREATE TABLE IF NOT EXISTS session_results (
    id              SERIAL      PRIMARY KEY,
    year            INT         NOT NULL,
    round           INT         NOT NULL,
    session_type    TEXT        NOT NULL,  -- 'R', 'Q', 'S', 'SQ'
    driver_abbr     TEXT        NOT NULL,
    full_name       TEXT        NOT NULL,
    team_name       TEXT        NOT NULL,
    position        INT,
    grid_position   INT,
    time_ms         DOUBLE PRECISION,     -- race time or qualifying time
    status          TEXT,                  -- 'Finished', '+1 Lap', 'DNF', etc.
    points          DOUBLE PRECISION DEFAULT 0,
    q1_ms           DOUBLE PRECISION,
    q2_ms           DOUBLE PRECISION,
    q3_ms           DOUBLE PRECISION,
    best_lap_ms     DOUBLE PRECISION,
    UNIQUE (year, round, session_type, driver_abbr)
);

CREATE INDEX IF NOT EXISTS idx_results_year_round ON session_results (year, round);
CREATE INDEX IF NOT EXISTS idx_results_session ON session_results (year, round, session_type);
CREATE INDEX IF NOT EXISTS idx_results_driver ON session_results (driver_abbr);

-- ==========================================
-- DRIVER STANDINGS (after each round)
-- ==========================================
CREATE TABLE IF NOT EXISTS driver_standings (
    id              SERIAL      PRIMARY KEY,
    year            INT         NOT NULL,
    round           INT         NOT NULL,  -- standings after this round
    driver_id       TEXT        NOT NULL,  -- e.g. 'max_verstappen'
    driver_abbr     TEXT,
    full_name       TEXT        NOT NULL,
    team_name       TEXT        NOT NULL,
    position        INT         NOT NULL,
    points          DOUBLE PRECISION DEFAULT 0,
    wins            INT         DEFAULT 0,
    UNIQUE (year, round, driver_id)
);

CREATE INDEX IF NOT EXISTS idx_dstandings_year ON driver_standings (year, round);

-- ==========================================
-- CONSTRUCTOR STANDINGS (after each round)
-- ==========================================
CREATE TABLE IF NOT EXISTS constructor_standings (
    id              SERIAL      PRIMARY KEY,
    year            INT         NOT NULL,
    round           INT         NOT NULL,
    constructor_id  TEXT        NOT NULL,  -- e.g. 'red_bull'
    constructor_name TEXT       NOT NULL,
    position        INT         NOT NULL,
    points          DOUBLE PRECISION DEFAULT 0,
    wins            INT         DEFAULT 0,
    UNIQUE (year, round, constructor_id)
);

CREATE INDEX IF NOT EXISTS idx_cstandings_year ON constructor_standings (year, round);
