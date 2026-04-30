# Scripts

Operational scripts for managing infrastructure and simulating live race data.

## infra.sh

Start, stop, or check the status of the GCE production VM.

```bash
# Start the VM
./scripts/infra.sh start

# Stop the VM (saves cost when idle)
./scripts/infra.sh stop

# Check VM status and external IP
./scripts/infra.sh status
```

**Prerequisites:** `gcloud` CLI authenticated with access to the project.

**Hardcoded values:**
- Project: `<PROJECT_ID>`
- Zone: `asia-southeast1-b`
- VM name: `f1-chubby-vm`

## simulate_race_to_influxdb.py

Replays a cached FastF1 race session and feeds lap-by-lap data into InfluxDB (or Pub/Sub). Used for demo and testing purposes.

### Usage

```bash
# Default: replay at 1 lap/sec → InfluxDB
python scripts/simulate_race_to_influxdb.py

# Faster replay: 5 laps/sec
python scripts/simulate_race_to_influxdb.py --speed 5

# Publish to Pub/Sub instead (tests the full Dataproc pipeline)
python scripts/simulate_race_to_influxdb.py --pubsub --gcp-project ${PROJECT_ID}

# Delete all simulation data from InfluxDB
python scripts/simulate_race_to_influxdb.py --teardown
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB connection URL |
| `INFLUXDB_TOKEN` | `f1chubby-influx-token` | InfluxDB admin token |
| `INFLUXDB_ORG` | `f1chubby` | InfluxDB organization |
| `INFLUXDB_BUCKET` | `live_race` | InfluxDB bucket |
| `MODEL_API_URL` | `http://localhost:8080` | Model API URL (for prediction calls during simulation) |

### Prerequisites

- `f1_cache/` directory with cached session data for the target race
- Running InfluxDB (or Pub/Sub credentials for `--pubsub` mode)
- Running Model API (for prediction generation during simulation)
- Python packages: `fastf1`, `influxdb-client`, `requests`, `pandas`

### What It Writes

| InfluxDB Measurement | Content |
|---------------------|---------|
| `live_timing` | Position, gap, interval, lap time, tyre data per driver per lap |
| `predictions` | Win/podium probabilities from Model API |
| `live_race_control` | Simulated race control messages (flags, incidents) |

---

← Back to [ReadMe.md](../ReadMe.md)
