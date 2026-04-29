# Streaming Consumers

Lightweight Python pull consumers that bridge **Google Pub/Sub** and **InfluxDB** for live race data.

## Architecture

Two independent consumers run in parallel:

| Consumer | Subscriptions | Output | Latency |
|----------|--------------|--------|---------|
| **Fast path** (`streaming_fast.py`) | `f1-timing-viz-fast`, `f1-race-control-viz-fast` | InfluxDB `live_timing` + `live_race_control` measurements | ~500 ms |
| **Slow path** (`streaming_slow.py`) | `f1-timing-pred-slow` | Calls Model API → InfluxDB `predictions` measurement | ~10 s |

```
Pub/Sub ──→ streaming-fast ──→ InfluxDB (timing + race control)
Pub/Sub ──→ streaming-slow ──→ Model API ──→ InfluxDB (predictions)
```

**Demo capability:** Kill the slow-path job → fast-path continues uninterrupted, proving the two paths are fully decoupled.

## Prerequisites

- Running InfluxDB instance (port 8086)
- GCP credentials with Pub/Sub subscriber access
- For slow path: running Model API (port 8080)

## Run with Docker (recommended)

The production `docker-compose.yml` includes both consumers. To run them alongside the main stack:

```bash
# Ensure influxdb and model-api are running
docker compose up streaming-fast streaming-slow
```

Or build and run the consumer image standalone:

```bash
docker build -t f1-streaming ./streaming

# Fast path
docker run --rm \
  --network host \
  f1-streaming \
  python streaming_fast.py \
    --project ${PROJECT_ID} \
    --influxdb-url http://localhost:8086 \
    --influxdb-token f1chubby-influx-token

# Slow path
docker run --rm \
  --network host \
  f1-streaming \
  python streaming_slow.py \
    --project ${PROJECT_ID} \
    --influxdb-url http://localhost:8086 \
    --influxdb-token f1chubby-influx-token \
    --model-api-url http://localhost:8080
```

## Run Directly

```bash
pip install google-cloud-pubsub influxdb-client requests

# Fast path
python streaming/streaming_fast.py \
  --project ${PROJECT_ID} \
  --influxdb-url http://localhost:8086 \
  --influxdb-token f1chubby-influx-token

# Slow path
python streaming/streaming_slow.py \
  --project ${PROJECT_ID} \
  --influxdb-url http://localhost:8086 \
  --influxdb-token f1chubby-influx-token \
  --model-api-url http://localhost:8080
```

## CLI Arguments

### streaming_fast.py

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--project` | Yes | — | GCP project ID |
| `--influxdb-url` | Yes | — | InfluxDB URL |
| `--influxdb-token` | Yes | — | InfluxDB admin token |
| `--influxdb-org` | No | `f1chubby` | InfluxDB organization |
| `--influxdb-bucket` | No | `live_race` | InfluxDB bucket |
| `--timing-sub` | No | `f1-timing-viz-fast` | Pub/Sub subscription for timing messages |
| `--rc-sub` | No | `f1-race-control-viz-fast` | Pub/Sub subscription for race-control messages |
| `--duration` | No | `1800` | Max run time in seconds (0 = unlimited) |

### streaming_slow.py

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--project` | Yes | — | GCP project ID |
| `--influxdb-url` | Yes | — | InfluxDB URL |
| `--influxdb-token` | Yes | — | InfluxDB admin token |
| `--influxdb-org` | No | `f1chubby` | InfluxDB organization |
| `--influxdb-bucket` | No | `live_race` | InfluxDB bucket |
| `--model-api-url` | Yes | — | Model API base URL |
| `--timing-sub` | No | `f1-timing-pred-slow` | Pub/Sub subscription for timing messages |
| `--duration` | No | `1800` | Max run time in seconds (0 = unlimited) |

## InfluxDB Measurements

| Measurement | Tags | Fields | Written By |
|------------|------|--------|-----------|
| `live_timing` | `race_id`, `driver` | `position`, `gap_to_leader`, `interval`, `lap_time_ms`, `compound`, `tyre_life`, `lap_number` | Fast path |
| `live_race_control` | `race_id`, `category` | `message`, `flag`, `elapsed_sec` | Fast path |
| `predictions` | `race_id`, `driver` | `win_prob`, `podium_prob`, `lap_number` | Slow path |

## Relationship to `spark/` Directory

The `streaming/` directory contains **Docker-packaged** consumers using the plain Python Pub/Sub client. The `spark/` directory contains equivalent Spark-based versions designed to run on **Google Dataproc**. Both consume the same Pub/Sub subscriptions and write to the same InfluxDB measurements.

---

← Back to [ReadMe.md](../ReadMe.md)
