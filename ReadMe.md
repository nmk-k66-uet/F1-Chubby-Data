# F1 Data Analytics & Live Race Predictor

A Formula 1 data analytics and real-time prediction system built on **Streamlit**. Provides race strategy visualizations, telemetry analysis, and ML-powered win/podium probability predictions lap-by-lap.

## Key Features

- **Real-time Simulation & Leaderboard** — simulates a live race data stream with a continuously updating Timing Tower and Interval/Gap tracking
- **Dynamic ML Predictor** — Random Forest models infer Win and Podium probabilities lap-by-lap, visualized through Sparklines and Radar Charts
- **Track Dominance & Telemetry** — speed, throttle, and RPM analysis across mini-sectors
- **Comprehensive Analytics** — lap times, tire strategies, and season standings

## Architecture

The application runs as a multi-service Docker Compose stack:

| Service | Description |
|---------|-------------|
| **Streamlit** | Dashboard UI (port 80 prod / 8501 dev) |
| **Model API** | FastAPI ML inference service (port 8080) |
| **InfluxDB** | Time-series DB for live race telemetry (port 8086) |
| **Streaming Fast** | Pub/Sub → InfluxDB consumer for live positions/timing/race control |
| **Streaming Slow** | Pub/Sub → Model API → InfluxDB consumer for predictions |

Historical data is served from **GCS + FastF1 cache** (`f1_cache/`). Live race data flows through **Pub/Sub** into **InfluxDB** via two lightweight Python pull consumers.

## Directory Structure

```
F1-Chubby-Data/
├── main.py                      # Streamlit entry point
├── Dockerfile                   # Streamlit container image
├── docker-compose.yml           # Production stack (5 services)
├── docker-compose.dev.yml       # Dev stack (3 services, hot reload)
├── requirements-streamlit.txt   # Streamlit dependencies
│
├── pages/                       # Streamlit multi-page app
│   ├── home.py                  # Season overview, standings, countdown
│   ├── race_analytics.py        # Race calendar + video intro
│   ├── details.py               # Analytics tabs for a selected race
│   ├── drivers.py               # Driver standings
│   └── constructors.py          # Constructor standings
│
├── components/                  # Reusable UI modules
│   ├── tab_live_race.py         # Live simulation (Timing Tower, ML Inspector)
│   ├── tab_telemetry.py         # Telemetry charts
│   ├── tab_track_dominance.py   # Track dominance map
│   ├── tab_lap_times.py         # Lap time comparison
│   ├── tab_strategy.py          # Tire strategy
│   ├── tab_positions.py         # Position changes
│   ├── tab_results.py           # Race classification
│   ├── tab_race_control.py      # Race control messages
│   ├── predictor_ui.py          # Pre-race prediction UI
│   └── replay_engine.py         # Race replay engine
│
├── core/                        # Backend logic
│   ├── data_loader.py           # GCS + FastF1 data loading with caching
│   ├── ml_core.py               # ML training, feature engineering, inference
│   ├── config.py                # Constants, team colors, flags
│   ├── data_crawler.py          # Historical data crawler → GCS
│   └── gcs_utils.py             # GCS utility functions
│
├── model_serving/               # ML prediction API
│   ├── app.py                   # FastAPI endpoints
│   ├── Dockerfile               # Model API image
│   └── requirements.txt         # ML dependencies
│
├── streaming/                   # Pub/Sub consumers (Docker)
│   ├── streaming_fast.py        # Fast path: Pub/Sub → InfluxDB
│   ├── streaming_slow.py        # Slow path: Pub/Sub → Model API → InfluxDB
│   └── Dockerfile               # Consumer image
│
├── scripts/                     # Operational scripts
│   ├── infra.sh                 # Start/stop GCP VM
│   └── simulate_race_to_influxdb.py  # Race replay → Pub/Sub/InfluxDB
│
├── infra/                       # Terraform (GCP infrastructure)
├── schemas/                     # Pub/Sub message schemas
├── assets/                      # Images, models, static files
└── f1_cache/                    # FastF1 cached session data
```

## Quick Start (Local Dev)

```bash
cp .env.dev.example .env
docker compose -f docker-compose.dev.yml up --build
# Open http://localhost:8501
```

See [streamlit_local_dev.md](streamlit_local_dev.md) for the full local development guide.

## Production Deployment

The production stack runs on a GCE VM via `docker-compose.yml` with 5 services (Streamlit, Model API, InfluxDB, streaming-fast, streaming-slow). Deployment is automated via GitHub Actions on push to `main`.
