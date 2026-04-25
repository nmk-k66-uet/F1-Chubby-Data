# Streamlit Local Development Guide

## Prerequisites

- **Docker** & **Docker Compose** (v2+)
- The model files in `assets/Models/`:
  - `podium_model.pkl`
  - `in_race_win_model.pkl`
  - `in_race_podium_model.pkl`
- The FastF1 cache directory `f1_cache/` (should already exist in the repo with ~800MB of cached session data for 2024–2026)

## Quick Start

```bash
# 1. Create your .env file
cp .env.dev.example .env

# 2. Start all services
docker compose -f docker-compose.dev.yml up --build
```

The app is available at **http://localhost:8501**.

## What Happens on Startup

1. **postgres** starts and auto-creates the schema from `sql/init.sql`
2. **influxdb** and **model-api** start in parallel
3. **etl** runs (depends on postgres being healthy):
   - Checks if `session_results` table already has data → **skips if already seeded**
   - Runs in **offline mode** — reads only from the local `f1_cache/` directory, no external API calls
   - Loads race calendar, session results, and standings for 2024–2026 into PostgreSQL
   - Exits with code 0
4. **streamlit** starts only after ETL exits successfully

On subsequent `docker compose up`, the ETL detects existing data and exits in ~1 second.

## Architecture

The dev stack runs 5 services (4 long-running + 1 one-shot ETL):

| Service | Port | Description |
|---------|------|-------------|
| **streamlit** | `8501` | Streamlit dashboard (production uses port 80) |
| **model-api** | `8080` | FastAPI ML prediction service |
| **postgres** | `5432` | PostgreSQL 15 (replaces Cloud SQL) |
| **influxdb** | `8086` | InfluxDB 2.7 for live race telemetry |
| **etl** | — | One-shot: seeds PostgreSQL from `f1_cache/`, then exits |

```
                          ┌───────────┐
                     ┌───▶│ Model API │
                     │    │   :8080   │
┌──────────┐         │    └───────────┘
│   ETL    │─(seeds)─┤
│ (offline)│         │    ┌──────────┐
└──────────┘         └───▶│ Postgres │◀──── Streamlit
                          │  :5432   │
                          └──────────┘

┌──────────┐     ┌──────────┐
│ Streamlit│────▶│ InfluxDB │
│  :8501   │     │  :8086   │
└──────────┘     └──────────┘
```

## Data Setup

### Sources of Truth

| Data Type | Source of Truth | Stored In | Fallback |
|-----------|----------------|-----------|----------|
| Calendar, results, standings | FastF1 cache → PostgreSQL (via ETL) | `postgres` container (`pgdata` volume) | FastF1 API (if PG empty) |
| Telemetry, lap data, weather | FastF1 cache | `f1_cache/` directory (bind-mounted) | FastF1 API (live/uncached sessions) |
| ML predictions | Model `.pkl` files | `assets/Models/` (bind-mounted to model-api) | None |
| Live race telemetry | InfluxDB | `influxdb` container (`influxdb-data` volume) | None |

### FastF1 Cache (`f1_cache/`)

The `f1_cache/` directory is shared between the ETL and Streamlit containers via bind mount. It contains:

| Contents | Purpose |
|----------|---------|
| `fastf1_http_cache.sqlite` | HTTP response cache (all API calls) |
| `2024/`, `2025/`, `2026/` | Parsed session data (laps, telemetry, weather) |

- **ETL** reads from this cache in offline mode to populate PostgreSQL (no outbound API calls)
- **Streamlit** reads from this cache for telemetry/lap data (`load_f1_session()`)
- Once a session is cached, all subsequent loads are local reads — no network call

### PostgreSQL Schema

Auto-created from `sql/init.sql` on first postgres startup. Four tables:

- `race_calendar` — race schedule (year, round, event name, country, circuit)
- `session_results` — per-driver results for R/Q/S sessions (position, time, points, best lap)
- `driver_standings` — cumulative standings after each round
- `constructor_standings` — cumulative standings after each round

### Model Files

The model-api loads `.pkl` files from `assets/Models/` via read-only bind mount:

- `podium_model.pkl` — pre-race podium probability
- `in_race_win_model.pkl` — live race win probability
- `in_race_podium_model.pkl` — live race podium probability

No GCS auth or downloads needed — production uses GCS, dev uses local files.

### Data Flow: Streamlit reads

```
Streamlit page request
  │
  ├─ Calendar/Results/Standings?
  │   └─ core/data_loader.py → core/db.py → PostgreSQL
  │       └─ (fallback: FastF1 API if PG returns empty)
  │
  ├─ Telemetry/Laps?
  │   └─ core/data_loader.py → FastF1 → f1_cache/ (local read if cached)
  │
  ├─ ML Prediction?
  │   └─ components/predictor_ui.py → HTTP POST → model-api:8080
  │
  └─ Live Race Data?
      └─ components/tab_live_race.py → InfluxDB:8086
```

## Hot Reload

Source code is bind-mounted into the containers, so changes to these files are reflected without rebuilding:

- `main.py`, `core/`, `components/`, `pages/`, `assets/` → Streamlit container
- `model_serving/app.py` → Model API container (uvicorn `--reload` enabled)
- `assets/Models/*.pkl` → Model API (restart model-api to pick up new models)

If you change `requirements-streamlit.txt`, `Dockerfile`, or `model_serving/requirements.txt`, rebuild:

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Environment Variables

All defaults are set in `docker-compose.dev.yml`. The `.env` file only needs:

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_PASSWORD` | `localdev123` | PostgreSQL password |
| `INFLUXDB_TOKEN` | `f1chubby-influx-token` | InfluxDB admin token |
| `INFLUXDB_PASSWORD` | `f1chubby2026` | InfluxDB admin password |

## Differences from Production

| Aspect | Production (`docker-compose.yml`) | Dev (`docker-compose.dev.yml`) |
|--------|----------------------------------|-------------------------------|
| PostgreSQL | Cloud SQL (external) | Local container with auto-schema |
| ETL | Runs separately via `scripts/load_historical_data.py` | Runs automatically on first `up`, offline mode |
| Models | Downloaded from GCS on startup | Bind-mounted from `assets/Models/` |
| Streamlit port | 80 | 8501 |
| Model API port | Internal only | Exposed on 8080 |
| Source code | Baked into Docker image | Bind-mounted (hot reload) |
| Model API mode | `uvicorn app:app` | `uvicorn app:app --reload` |
| GCS auth | VM service account | Not needed |
| FastF1 cache | Persistent volume on VM | Bind-mounted from host `f1_cache/` |

## Common Tasks

### Restart a single service

```bash
docker compose -f docker-compose.dev.yml restart streamlit
```

### View logs

```bash
# All services
docker compose -f docker-compose.dev.yml logs -f

# Single service
docker compose -f docker-compose.dev.yml logs -f model-api
```

### Re-seed PostgreSQL (force)

```bash
docker compose -f docker-compose.dev.yml down -v  # removes pgdata volume
docker compose -f docker-compose.dev.yml up --build
```

This drops all data and re-runs the ETL from `f1_cache/`.

### Test the model API directly

```bash
# Health check
curl http://localhost:8080/health

# Pre-race prediction
curl -X POST http://localhost:8080/predict-prerace \
  -H "Content-Type: application/json" \
  -d '{"drivers": [{"driver": "VER", "GridPosition": 1, "TeamTier": 1, "QualifyingDelta": 0.0}]}'
```

### Connect to PostgreSQL

```bash
docker exec -it f1-postgres psql -U f1admin -d f1chubby

# Example queries:
SELECT count(*) FROM session_results;
SELECT * FROM race_calendar WHERE year = 2026 ORDER BY round;
SELECT * FROM driver_standings WHERE year = 2026 AND round = (SELECT max(round) FROM driver_standings WHERE year = 2026);
```

### Stop everything

```bash
docker compose -f docker-compose.dev.yml down
```

## Troubleshooting

**ETL says "Blocked by --offline" and skips sessions**
→ The session isn't in `f1_cache/`. This is expected for future/unraced rounds. The Streamlit app will fall back to the FastF1 API for those sessions at runtime.

**Model API shows "Model file missing"**
→ Check that `assets/Models/` contains the 3 `.pkl` files. If not, download from GCS:
```bash
gsutil cp gs://f1chubby-model-gen-lang-client-0314607994/*.pkl assets/Models/
```

**Streamlit can't connect to PostgreSQL**
→ The `postgres` container must be healthy before Streamlit starts. Check: `docker ps` — if postgres shows `(unhealthy)`, check its logs.

**Streamlit doesn't start (waiting for ETL)**
→ The ETL must exit with code 0 before Streamlit starts. Check `docker compose -f docker-compose.dev.yml logs etl` for errors. Common cause: the Streamlit Docker image doesn't have `psycopg2-binary` — verify it's in `requirements-streamlit.txt`.

**Port conflict**
→ If 8501, 8080, 5432, or 8086 are already in use, either stop the conflicting service or change the host port in `docker-compose.dev.yml` (e.g., `"5433:5432"`).
