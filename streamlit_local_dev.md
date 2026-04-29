# Local Development Guide

## Prerequisites

- **Docker** & **Docker Compose** (v2+)
- The model files in `assets/Models/`:
  - `podium_model.pkl`
  - `in_race_win_model.pkl`
  - `in_race_podium_model.pkl`
- The FastF1 cache directory `f1_cache/` (~800 MB of cached session data for 2024–2026)

## Quick Start

```bash
# 1. Create your .env file
cp .env.dev.example .env

# 2. Start all services
docker compose -f docker-compose.dev.yml up --build
```

The app is available at **http://localhost:8501**.

## What Happens on Startup

1. **influxdb** and **model-api** start in parallel
2. **streamlit** starts once both are up

## Architecture

The dev stack runs 3 long-running services:

| Service | Port | Description |
|---------|------|-------------|
| **streamlit** | `8501` | Streamlit dashboard (production uses port 80) |
| **model-api** | `8080` | FastAPI ML prediction service |
| **influxdb** | `8086` | InfluxDB 2.7 for live race telemetry |

```
┌──────────┐     ┌───────────┐
│ Streamlit│────▶│ Model API │
│  :8501   │     │   :8080   │
└────┬─────┘     └───────────┘
     │
     │           ┌──────────┐
     └──────────▶│ InfluxDB │
                 │  :8086   │
                 └──────────┘
```

## Data

### Sources of Truth

| Data Type | Source | Stored In | Fallback |
|-----------|--------|-----------|----------|
| Calendar, results, standings | GCS / FastF1 cache | `f1_cache/` directory (bind-mounted) | FastF1 API (uncached sessions) |
| Telemetry, lap data, weather | FastF1 cache | `f1_cache/` directory (bind-mounted) | FastF1 API (uncached sessions) |
| ML predictions | Model `.pkl` files | `assets/Models/` (bind-mounted to model-api) | None |
| Live race telemetry | InfluxDB | `influxdb` container (`influxdb-data` volume) | None |

### FastF1 Cache (`f1_cache/`)

The `f1_cache/` directory is bind-mounted into the Streamlit container:

| Contents | Purpose |
|----------|---------|
| `fastf1_http_cache.sqlite` | HTTP response cache (all API calls) |
| `2024/`, `2025/`, `2026/` | Parsed session data (laps, telemetry, weather) |

Once a session is cached, all subsequent loads are local reads — no network call.

### Model Files

The model-api loads `.pkl` files from `assets/Models/` via read-only bind mount:

- `podium_model.pkl` — pre-race podium probability
- `in_race_win_model.pkl` — live race win probability
- `in_race_podium_model.pkl` — live race podium probability

No GCS auth needed — production uses GCS, dev uses local files.

### Data Flow

```
Streamlit page request
  │
  ├─ Calendar/Results/Standings/Telemetry/Laps?
  │   └─ core/data_loader.py → FastF1 → f1_cache/ (local read if cached)
  │
  ├─ ML Prediction?
  │   └─ components/predictor_ui.py → HTTP POST → model-api:8080
  │
  └─ Live Race Data?
      └─ components/tab_live_race.py → InfluxDB:8086
```

## Hot Reload

Source code is bind-mounted into the containers, so changes are reflected without rebuilding:

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
| `INFLUXDB_TOKEN` | `f1chubby-influx-token` | InfluxDB admin token |
| `INFLUXDB_PASSWORD` | `f1chubby2026` | InfluxDB admin password |

## Differences from Production

| Aspect | Production (`docker-compose.yml`) | Dev (`docker-compose.dev.yml`) |
|--------|----------------------------------|-------------------------------|
| Models | Downloaded from GCS on startup | Bind-mounted from `assets/Models/` |
| Streamlit port | 80 | 8501 |
| Model API port | Internal only | Exposed on 8080 |
| Source code | Baked into Docker image | Bind-mounted (hot reload) |
| Model API mode | `uvicorn app:app` | `uvicorn app:app --reload` |
| Streaming consumers | Run as containers (`streaming-fast`, `streaming-slow`) | Not included (use production compose or run manually) |
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

### Reset data

```bash
docker compose -f docker-compose.dev.yml down -v  # removes InfluxDB volume
docker compose -f docker-compose.dev.yml up --build
```

### Test the model API directly

```bash
# Health check
curl http://localhost:8080/health

# Pre-race prediction
curl -X POST http://localhost:8080/predict-prerace \
  -H "Content-Type: application/json" \
  -d '{"drivers": [{"driver": "VER", "GridPosition": 1, "TeamTier": 1, "QualifyingDelta": 0.0}]}'
```

### Stop everything

```bash
docker compose -f docker-compose.dev.yml down
```

## Troubleshooting

**Model API shows "Model file missing"**
→ Check that `assets/Models/` contains the 3 `.pkl` files. If not, download from GCS:
```bash
gsutil cp gs://f1chubby-model-${PROJECT_ID}/*.pkl assets/Models/
```

**Port conflict**
→ If 8501, 8080, or 8086 are already in use, either stop the conflicting service or change the host port in `docker-compose.dev.yml`.

---

## Running Without Docker

If you prefer running the Streamlit app directly on your host (e.g. for faster iteration or IDE debugging):

### Prerequisites

- Python 3.11+
- Model API and InfluxDB running separately (via Docker or otherwise)
- `f1_cache/` directory with cached session data
- `assets/Models/` with the 3 `.pkl` files (only needed if running model-api locally too)

### Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 2. Install dependencies
pip install -r requirements-streamlit.txt

# 3. Start supporting services (in another terminal)
docker compose -f docker-compose.dev.yml up influxdb model-api

# 4. Set environment variables
export MODEL_API_URL=http://localhost:8080
export INFLUXDB_URL=http://localhost:8086
export INFLUXDB_TOKEN=f1chubby-influx-token
export INFLUXDB_ORG=f1chubby
export INFLUXDB_BUCKET=live_race

# 5. Run Streamlit
streamlit run main.py
```

The app is available at **http://localhost:8501**.

### LOCAL_MODE (FastF1-only, no external services)

If you don't need live race features and just want to browse historical data:

```bash
export LOCAL_MODE=true
streamlit run main.py
```

This bypasses InfluxDB queries and Model API calls. Calendar, results, standings, telemetry, and lap data all load from `f1_cache/` or the FastF1 API directly.

---

← Back to [ReadMe.md](ReadMe.md)
