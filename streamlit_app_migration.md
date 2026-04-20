# Streamlit App Migration Summary

**Branch:** `feature/migrate-streamlit-coupled-app`  
**Date:** 2026-04-20  
**Scope:** 31 files changed

---

## 1. Architecture Changes

### Before
- Monolithic Streamlit app with ML models loaded in-process (`joblib`/`scikit-learn`)
- All historical data fetched live from Ergast API and FastF1 on every page load
- Single `Dockerfile`, no orchestration
- Deployed as a standalone container on port 8501

### After
- **3-service docker-compose** architecture:
  - `streamlit` — UI only (port 80 → 8501)
  - `model-api` — FastAPI ML inference service (port 8080, internal)
  - `influxdb` — Time-series DB for live race telemetry (port 8086)
- Historical data served from **Cloud SQL PostgreSQL** with FastF1 fallback
- ML dependencies (`scikit-learn`, `joblib`) removed from Streamlit container
- `LOCAL_MODE` env var for development without PostgreSQL/InfluxDB

---

## 2. New Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates streamlit + model-api + influxdb services |
| `.env.example` | Template for environment variables (PG, InfluxDB, GCS) |
| `core/db.py` | PostgreSQL connection pool + query helper with graceful fallback |
| `model_serving/app.py` | FastAPI ML serving app (`/predict-inrace`, `/predict-prerace`, `/health`) — downloads models from GCS on startup |
| `model_serving/Dockerfile` | Python 3.11-slim image for model API |
| `model_serving/requirements.txt` | ML deps: fastapi, scikit-learn, joblib, google-cloud-storage |
| `model_serving/models/.gitkeep` | Placeholder for local model files |
| `requirements-streamlit.txt` | Streamlit-only deps (no ML libraries) |
| `sql/init.sql` | PostgreSQL schema: `race_calendar`, `session_results`, `driver_standings`, `constructor_standings` |
| `scripts/load_historical_data.py` | One-time ETL: FastF1 → Cloud SQL (calendar, results, standings for 2024-2026) |

---

## 3. Modified Files

### `core/data_loader.py` (153 insertions, rewrite)
- **Before:** Fetched everything from Ergast API + FastF1 on every call
- **After:** Priority chain — PostgreSQL first, FastF1 fallback
- Key functions changed:
  - `get_schedule(year)` — queries `race_calendar` table, falls back to FastF1
  - `get_race_winner(year, round)` — queries `session_results` table
  - `get_event_highlights(year, round)` — queries `session_results` for podium + fastest lap
  - `load_f1_session(year, round, session_type)` — unchanged (always FastF1 for live telemetry)

### `components/predictor_ui.py` (+115 lines)
- **Before:** Called `ml_core` directly (in-process `joblib.load()`)
- **After:** HTTP calls to `model-api:8080` endpoints via `requests.post()`
- Endpoints used: `POST /predict-inrace`, `POST /predict-prerace`
- Falls back to error message if model-api is unreachable

### `components/tab_live_race.py` (+102 lines)
- **Before:** In-memory race state only
- **After:** Writes live telemetry to InfluxDB via `influxdb_client` for persistence and Grafana dashboards

### `pages/home.py` (+62 lines)
- **Before:** Ergast API calls for schedule and recent results
- **After:** Uses `data_loader.get_schedule()` (PG-backed) and `data_loader.get_race_winner()`

### `pages/drivers.py` (+55 lines)
- **Before:** Ergast API for driver standings
- **After:** Queries `driver_standings` table via `core.db.query()`

### `pages/constructors.py` (+45 lines)
- **Before:** Ergast API for constructor standings
- **After:** Queries `constructor_standings` table via `core.db.query()`

### `Dockerfile` (Streamlit container)
- Uses `requirements-streamlit.txt` instead of `requirements.txt`
- Adds `libpq-dev` for `psycopg2`
- Adds `HEALTHCHECK` on `/_stcore/health`
- Copies `sql/` directory
- Runs on port 8501 internally, mapped to 80 by docker-compose

### `infra/modules/networking/main.tf`
- Firewall rule updated: `allowed_ports` now includes port `80` (HTTP for Streamlit)

### `infra/` (multiple files)
- **Removed:** Cloud Run module from Terraform (`module "cloudrun"` in `main.tf`, output in `outputs.tf`, `streamlit_image` variable)
- **Updated:** Project ID to `gen-lang-client-0314607994`
- **Added:** Static IP resource `google_compute_address.f1_static_ip` in compute module
- **Added:** `region` variable to compute module
- **Added:** TFC dynamic credential variables (`TFC_GCP_PROVIDER_AUTH`, `TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL`)

### `.github/workflows/`
- **Deleted:** `deploy-streamlit.yml` (was Cloud Run deployment, no longer used)
- **Rewritten:** `deploy-vm.yml` — now deploys full Streamlit app + model serving to VM via SCP + docker compose
- **Fixed:** Project ID in `deploy-dataproc.yml` and `upload-data.yml`

### `.gitignore`
- Added: `.env`, `f1_cache/`, `model_serving/models/*.pkl`, `model_serving/models/*.joblib`

### `.streamlit/config.toml`
- Added `[browser]` section: `gatherUsageStats = false`
- Added `[server]` section: `enableWebsocketCompression = true`

### `revised_plan.md` / `team_assignment.md`
- Updated to reflect new architecture, task assignments, and deployment status

---

## 4. Database Schema

```sql
-- race_calendar: year, round, event_name, country, event_date, circuit, event_format
-- session_results: year, round, session_type, driver_abbr, full_name, team_name,
--                  position, grid_position, time_ms, status, points, q1/q2/q3_ms, best_lap_ms
-- driver_standings: year, round, driver_id, driver_abbr, full_name, team_name, position, points, wins
-- constructor_standings: year, round, constructor_id, constructor_name, position, points, wins
```

Data loaded: **2,311 session results** + standings across 2024 (24 rounds), 2025 (24 rounds), 2026 (3 rounds).

---

## 5. Deployment Topology

```
Internet → Cloudflare (SSL Flexible) → f1.thedblaster.id.vn
  → GCE VM <VM_IP> (static IP, port 80)
    → docker-compose:
        ├── f1-streamlit  (port 80 → 8501)
        ├── f1-model-api  (port 8080, internal only)
        └── f1-influxdb   (port 8086)
  → Cloud SQL <CLOUD_SQL_IP> (PostgreSQL 15, db=f1chubby)
```

---

## 6. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | *(empty)* | Cloud SQL IP |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `f1chubby` | Database name |
| `POSTGRES_USER` | `postgres` | DB user |
| `POSTGRES_PASSWORD` | *(empty)* | DB password |
| `INFLUXDB_TOKEN` | `f1chubby-influx-token` | InfluxDB admin token |
| `INFLUXDB_PASSWORD` | `f1chubby2026` | InfluxDB admin password |
| `USE_GCS` | `true` | Model API: download models from GCS bucket on startup |
| `LOCAL_MODE` | `false` | Skip PG/InfluxDB, use FastF1 fallback only |
| `MODEL_API_URL` | `http://model-api:8080` | Set by docker-compose for streamlit |
| `INFLUXDB_URL` | `http://influxdb:8086` | Set by docker-compose for streamlit |
