# Model Serving API

FastAPI microservice for F1 race prediction inference. Serves 3 Random Forest models via REST endpoints.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Readiness check — reports which models are loaded |
| `POST` | `/predict-prerace` | Pre-race podium probabilities |
| `POST` | `/predict-inrace` | Live race win + podium probabilities |

## Local Development

### Prerequisites

- Python 3.11+
- Model files in `assets/Models/`:
  - `podium_model.pkl`
  - `in_race_win_model.pkl`
  - `in_race_podium_model.pkl`

### Run Directly

```bash
cd model_serving
pip install -r requirements.txt

# Point to local model files, disable GCS download
USE_GCS=false MODEL_DIR=../assets/Models uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### Run with Docker

```bash
# Build
docker build -t f1-model-api ./model_serving

# Run with local models (no GCS auth needed)
docker run -p 8080:8080 \
  -v ./assets/Models:/app/models:ro \
  -e USE_GCS=false \
  f1-model-api
```

### Run via Docker Compose (recommended)

```bash
docker compose -f docker-compose.dev.yml up model-api
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_DIR` | `/app/models` | Directory containing `.pkl` model files |
| `GCS_BUCKET` | `f1chubby-model` | GCS bucket name for model artifacts (prod only) |
| `USE_GCS` | `true` | Set to `false` for local development (skip GCS download) |

## API Reference

### `GET /health`

```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "models_loaded": {
    "pre_race": true,
    "in_race_win": true,
    "in_race_podium": true
  }
}
```

### `POST /predict-prerace`

Predicts podium probability for each driver based on pre-race data.

```bash
curl -X POST http://localhost:8080/predict-prerace \
  -H "Content-Type: application/json" \
  -d '{
    "drivers": [
      {"driver": "VER", "GridPosition": 1, "TeamTier": 1, "QualifyingDelta": 0.0, "FP2_PaceDelta": 0.0, "DriverForm": 0.8},
      {"driver": "NOR", "GridPosition": 2, "TeamTier": 1, "QualifyingDelta": 0.15, "FP2_PaceDelta": 0.1, "DriverForm": 0.7},
      {"driver": "LEC", "GridPosition": 3, "TeamTier": 1, "QualifyingDelta": 0.25, "FP2_PaceDelta": 0.2, "DriverForm": 0.6}
    ]
  }'
```

**Input features:**

| Field | Type | Description |
|-------|------|-------------|
| `driver` | string | Driver abbreviation (e.g. `VER`) |
| `GridPosition` | float | Starting grid position |
| `TeamTier` | float | Team strength tier (1 = top, 3 = backmarker) |
| `QualifyingDelta` | float | Gap to pole in qualifying (seconds) |
| `FP2_PaceDelta` | float | Gap to fastest FP2 long-run pace (seconds) |
| `DriverForm` | float | Recent driver form score (0–1) |

**Response:** `{"predictions": [{"driver": "VER", "podium_prob": 0.85}, ...]}`

### `POST /predict-inrace`

Predicts win and podium probability for each driver during a live race.

```bash
curl -X POST http://localhost:8080/predict-inrace \
  -H "Content-Type: application/json" \
  -d '{
    "drivers": [
      {"driver": "VER", "LapFraction": 0.5, "CurrentPosition": 1, "GapToLeader": 0.0, "TyreLife": 15, "CompoundIdx": 1, "IsPitOut": 0},
      {"driver": "NOR", "LapFraction": 0.5, "CurrentPosition": 2, "GapToLeader": 3.5, "TyreLife": 15, "CompoundIdx": 1, "IsPitOut": 0}
    ]
  }'
```

**Input features:**

| Field | Type | Description |
|-------|------|-------------|
| `driver` | string | Driver abbreviation |
| `LapFraction` | float | Race progress (0.0 = start, 1.0 = finish) |
| `CurrentPosition` | float | Current race position |
| `GapToLeader` | float | Gap to race leader (seconds) |
| `TyreLife` | float | Current tyre age in laps |
| `CompoundIdx` | float | Tyre compound index (0=SOFT, 1=MEDIUM, 2=HARD, 3=INTER, 4=WET) |
| `IsPitOut` | float | 1 if driver just exited pits, 0 otherwise |

**Response:** `{"predictions": [{"driver": "VER", "win_prob": 0.45, "podium_prob": 0.82}, ...]}`

---

← Back to [ReadMe.md](../ReadMe.md)
