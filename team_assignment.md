# Team Assignment — F1-Chubby-Data

> **5 members · Updated Apr 23, 2026**
> Focus: remaining pipeline integration work toward Demo Day

---

## Desired Outcome

A working end-to-end demo:

1. **Spark ETL** reads raw data from GCS → populates 4 PostgreSQL tables (race_calendar, session_results, driver_standings, constructor_standings)
2. **Spark Model Training** reads raw data from GCS → engineers features → trains pre-race + in-race models → uploads `.pkl` artifacts to GCS
3. **Simulation Service** replays a cached race into Pub/Sub at 5× speed
4. **Spark Streaming Fast Path** consumes Pub/Sub → writes live_positions, live_timing, live_race_control to InfluxDB (sub-second)
5. **Spark Streaming Slow Path** consumes Pub/Sub → collects features → calls Model Serving API (stateless inference) → Spark writes predictions to InfluxDB (10 sec trigger)
6. **Streamlit Dashboard** shows historical views from PostgreSQL, live race panels from InfluxDB, and pre-race predictions from Model API
7. **Key demo moment:** kill slow-path job → live visualization continues uninterrupted

---

## Project Status

### Completed (Phase 0 + Phase 1)

- [x] Terraform config (`infra/`) — all GCP resources provisioned
- [x] GCP infrastructure live: VM, Cloud SQL, Pub/Sub, GCS buckets, Dataproc API
- [x] Docker-compose (prod): Streamlit + Model Serving API + InfluxDB on VM
- [x] Docker-compose (dev): local dev stack with PostgreSQL, InfluxDB, Model API, ETL
- [x] Model Serving API (`model_serving/app.py`): FastAPI, loads models from GCS, endpoints working
- [x] ML models trained: `podium_model.pkl`, `in_race_win_model.pkl`, `in_race_podium_model.pkl` in GCS
- [x] MLCore (`core/ml_core.py`): pre-race + in-race training + inference
- [x] DataCrawler (`core/data_crawler.py`): feature extraction → CSV
- [x] ETL script (`scripts/load_historical_data.py`): FastF1 → PostgreSQL (4 tables, `--offline`, `--skip-if-seeded`)
- [x] PostgreSQL schema: 4 tables deployed (race_calendar, session_results, driver_standings, constructor_standings)
- [x] InfluxDB running on VM (org=f1chubby, bucket=live_race, currently empty)
- [x] Streamlit live at `https://f1.thedblaster.id.vn` — historical views from GCS via FastF1 cache, standings from Ergast API
- [x] Pre-race + in-race predictions route through Model Serving API
- [x] GitHub Actions workflows (terraform, deploy-vm, deploy-dataproc, upload-data)
- [x] Streamlit reads `predictions` measurement from InfluxDB (existing reader in `tab_live_race.py`)
- [x] DataCrawler data extraction → GCS upload (all historical data crawled and in GCS)
- [x] ETL historical data load (pre-seeded via CSV import into PostgreSQL)
- [x] Streamlit decoupled from PostgreSQL (reads from GCS + FastF1 cache, ADC auth)
- [x] GCS bidirectional caching in `core/data_loader.py` — `GCStorage` class downloads from / uploads to `f1chubby-raw` bucket; local cache cleaned after each session load
- [x] Deploy-VM workflow updated: does **not** copy `f1_cache` to VM (loaded on-demand from GCS); adds `sql/`, `simulation_service.py`, `schemas/**` to deploy paths
- [x] Deploy-Dataproc workflow: split `batch` into separate `etl` and `training` job types with dedicated pipeline scripts

### Not Started

- [ ] `spark/etl_pipeline.py` — Spark ETL job (GCS → PG) — **kept in design for presentation only, data pre-seeded**
- [ ] `spark/training_pipeline.py` — Spark Model Training job (GCS → features → train → .pkl → GCS)
- [x] `spark/streaming_fast.py` — Spark Streaming fast path (Pub/Sub → InfluxDB live measurements)
- [x] `spark/streaming_slow.py` — Spark Streaming slow path (Pub/Sub → features → Model API (stateless) → Spark writes predictions to InfluxDB)
- [x] Simulation Service — replay cached race into InfluxDB or Pub/Sub (`scripts/simulate_race_to_influxdb.py --pubsub`)
- [x] Pub/Sub message schemas (`schemas/timing.json`, `schemas/telemetry.json`, `schemas/race_control.json`)
- [ ] Streamlit live race panels: live_positions reader, live_timing reader, live_race_control reader
- [ ] Streamlit pipeline health panel (simplified — Model API health, InfluxDB freshness, Pub/Sub backlog)
- [ ] Slides

---

## Remaining Jobs & Assignments

### Team Overview

| Person | Focus | Key Deliverables |
|--------|-------|-----------------|
| **Hieu** | DataCrawler → GCS + Spark ETL | Extend DataCrawler with GCS upload, write `spark/etl_pipeline.py` |
| **Long** | Spark Model Training | Write `spark/training_pipeline.py` (feature eng → train → .pkl → GCS) |
| **Thanh** | Simulation + Streaming | SimService, Pub/Sub schemas, replay cache, `streaming_fast.py`, `streaming_slow.py` |
| **Duy** | Streamlit live race panels | InfluxDB readers for live_positions, live_timing, live_race_control; health panel |
| **Kien** | Slides | ML architecture, model serving, training approach slides |

### Dependency Chain

```
Hieu 0.3 (DataCrawler → GCS) ──→ Hieu 2.1a (Spark ETL → PG)
                                                        ↓
                                            Duy 2.7 (Streamlit PG queries) [already done]
                                            
Long 2.1b (Spark Training → .pkl → GCS) ──→ Model API loads new models
                                                        ↓
                                            Kien 2.4 was (now Thanh 2.4)

Thanh 0.4 (SimService) ──→ Thanh 0.4b (Schemas) ──→ Thanh 2.5 (Deploy Sim)
                                    ↓                          ↓
                           Thanh 2.3 (Fast Path) ──→ Thanh 2.4 (Slow Path)
                                    ↓
                           Duy 2.6 (Live panels read from InfluxDB)

No blocking dependency:
  Duy can build InfluxDB reader components NOW (query logic, UI, staleness indicators)
  and test with mock data or after Thanh's streaming populates InfluxDB.
```

---

### Hieu — Spark ETL (Presentation Only) + Assist Thanh

#### Task 0.3 — ~~Extend DataCrawler with GCS Upload~~ (Completed)

> **Status:** ✅ Completed. All historical data has been crawled and uploaded to GCS. Additionally, `core/data_loader.py` now has a `GCStorage` class and `load()` function that provides bidirectional GCS caching: downloads session cache from `f1chubby-raw` if available, falls back to FastF1, then uploads new cache to GCS. Local `f1_cache/` is cleaned after each session load — the VM no longer needs a pre-populated cache directory.

#### Task 2.1a — Spark ETL on Dataproc (Presentation Only)

| Field | Detail |
|-------|--------|
| **Est. Effort** | 0 hrs (pre-seeded, kept for presentation) |
| **Status** | Data pre-seeded via CSV import. Pipeline kept in architecture diagrams for demo presentation. |

> **Note:** Hieu's primary remaining work is to assist Thanh with streaming tasks (0.4, 2.3, 2.4) since Thanh has the heaviest remaining load.

---

### Long — Spark Model Training

#### Task 2.1b — Spark Model Training on Dataproc

| Field | Detail |
|-------|--------|
| **Est. Effort** | 5 hrs |
| **Depends On** | 0.3 (data in GCS) |
| **Blocks** | 2.2 (Model API loads models from GCS) |

Write `spark/training_pipeline.py` — reads raw data from GCS, engineers features, trains models, uploads artifacts.

- Read from `gs://f1chubby-raw/`
- PostgreSQL is available for training data storage (Long manages schema/usage freely)
- Feature Engineering: GridPosition, QualifyingDelta, FP2_PaceDelta, DriverForm, TeamTier (pre-race); lap-by-lap snapshots (in-race)
- Train pre-race RandomForest classifier → `pre_race_model.pkl`
- Train in-race RandomForest regressor → `in_race_model.pkl`, `in_race_podium_model.pkl`
- Upload `.pkl` artifacts to `gs://f1chubby-model/`
- Reference: existing training logic in `core/ml_core.py` (adapt for Spark scale)

**Done when:**
- [ ] Job completes on Dataproc (exit code 0)
- [ ] `gsutil ls gs://f1chubby-model/` shows all model files
- [ ] Models loadable via `joblib.load()` and callable with feature dicts
- [ ] Pre-race accuracy >50%, In-race MAE <3 positions

---

### Thanh — Simulation + Streaming (Fast + Slow Paths)

#### Task 0.4 — Build Simulation Service

| Field | Detail |
|-------|--------|
| **Est. Effort** | 4 hrs |
| **Depends On** | — |
| **Blocks** | 0.5, 2.5 |

Create Simulation Service — reads pre-cached race from GCS, replays to Pub/Sub at configurable speed.

- Publish to 3 topics: `f1-telemetry` (~10 Hz/car), `f1-timing` (per lap), `f1-race-control` (events)
- `REPLAY_SPEED` env var (default 5.0 → ~18 min race)
- JSON messages match schemas in `/schemas/`
- Graceful shutdown on SIGTERM

#### Task 0.4b — Pub/Sub Message Schemas

| Field | Detail |
|-------|--------|
| **Est. Effort** | 1.5 hrs |
| **Depends On** | — |
| **Blocks** | 2.3, 2.4 |

Define JSON Schema (draft-07) for all 3 topics in `schemas/`. Include `schemas/validate.py` utility.

#### Task 0.5 — Pre-Cache Race Replays

| Field | Detail |
|-------|--------|
| **Est. Effort** | 1 hr |
| **Depends On** | 0.4 |

Extract 2–3 races from FastF1, interpolate to 10 Hz, save as parquet. Upload to `gs://f1chubby-raw/replay/`.

#### Task 2.3 — Spark Streaming Fast Path

| Field | Detail |
|-------|--------|
| **Est. Effort** | 6 hrs |
| **Depends On** | 0.4b (schemas), InfluxDB running |
| **Blocks** | Duy 2.6 (live panels need data in InfluxDB) |

Write `spark/streaming_fast.py` — Pub/Sub → parse/validate → enrich metadata → InfluxDB.

- Subscriptions: `*-viz-fast`
- Output: `live_positions` (X/Y, speed, gear, drs), `live_timing` (position, lap_time, gap, tyre), `live_race_control` (flags, incidents)
- Latency: sub-second micro-batches (`processingTime="500ms"`)
- No ML dependency — independent of slow path

#### Task 2.4 — Spark Streaming Slow Path

| Field | Detail |
|-------|--------|
| **Est. Effort** | 7 hrs |
| **Depends On** | 0.4b, 2.1b (models in GCS), 2.2 (Model API deployed) |

Write `spark/streaming_slow.py` — Pub/Sub → windowed features → call Model API → InfluxDB predictions.

- Subscriptions: `*-pred-slow`
- 5–10 sec tumbling windows
- Batch driver features → `POST /predict-inrace`
- Output: InfluxDB `predictions` (driver_id, predicted_position, confidence, model_version)
- Graceful degradation: Model API down → log + skip window

#### Task 2.5 — Deploy Simulation on VM

| Field | Detail |
|-------|--------|
| **Est. Effort** | 2 hrs |
| **Depends On** | 0.4, Pub/Sub topics exist |

Deploy SimService container on VM. Verify messages arrive in all 3 Pub/Sub topics.

**Done when (all Thanh tasks):**
- [ ] SimService replays a race at 5× speed, messages in all 3 topics
- [ ] Fast path: data in InfluxDB live measurements within 1 second
- [ ] Slow path: predictions in InfluxDB within 10 seconds
- [ ] Kill slow path → fast path continues unaffected

---

### Duy — Streamlit Live Race Panels

#### Task 2.6 — Live Race InfluxDB Readers

| Field | Detail |
|-------|--------|
| **Est. Effort** | 5 hrs |
| **Depends On** | InfluxDB measurement schema (from Thanh's 0.4b) |
| **Blocks** | 2.9 (deploy), 3.6 (verify live views) |

Build 3 new Streamlit views that read from InfluxDB fast-path measurements. The `predictions` reader already exists in `components/tab_live_race.py` (`_fetch_predictions_from_influxdb()` at line 57) — use it as the template.

| Component | InfluxDB Measurement | What it Renders |
|-----------|---------------------|-----------------|
| Live Race Tracker | `live_positions` | Car X/Y positions on track map, auto-refresh 1s |
| Live Timing Board | `live_timing` | Positions, gaps, lap times, tyre compound per driver |
| Race Control Feed | `live_race_control` | Flags, safety car, incidents as scrollable feed |

- All views auto-refresh, handle "no data" gracefully ("Waiting for live data...")
- Use `influxdb-client` Python SDK (already a dependency)
- No imports from `core.ml_core` or `joblib`

#### Task 2.8 — Pipeline Health Panel (Simplified)

| Field | Detail |
|-------|--------|
| **Est. Effort** | 2 hrs |
| **Depends On** | 2.6 |

Simplified health panel:
- Model Serving API: `GET /health` → model version, loaded status
- InfluxDB freshness: last-write timestamp per measurement
- Pub/Sub backlog: subscription unacked message count (via Cloud Monitoring API)
- Auto-refresh every 30 seconds

**Done when (all Duy tasks):**
- [ ] 3 new live views visible in Streamlit
- [ ] Live Race Tracker shows car positions (or "Waiting for data..." when InfluxDB empty)
- [ ] Live Timing Board shows driver gaps, tyre info
- [ ] Race Control Feed shows flag events
- [ ] Health panel shows Model API health + InfluxDB freshness
- [ ] All views handle "no data" and component failures gracefully

---

### Kien — Slides

#### Slides — ML & Model Serving (2–3 slides)

| Field | Detail |
|-------|--------|
| **Est. Effort** | 3 hrs |
| **Presenter** | Kien (~4 min) |

Slide content:
1. Two ML models: features, algorithms, training approach, accuracy metrics
2. Model Serving API: interface contract, decoupled architecture, hot-swap capability
3. Streaming slow path: feature windowing → API call → InfluxDB predictions

Also help other team members with slide content for their sections.

---

## Remaining Timeline (Apr 21 → Demo Apr 25)

```
Apr 21–22 (2 days):
  Hieu:  Help Thanh with SimService + Schemas
  Long:  2.1b Spark Model Training pipeline
  Thanh: 0.4 SimService → 0.4b Schemas → 0.5 Replay cache
  Duy:   2.6 Streamlit live race panels (build readers, test with mock/empty data)
  Kien:  Slides (ML section)

Apr 23 (1 day):
  Hieu:  Help Thanh with streaming fast/slow paths
  Long:  Finish 2.1b → verify models in GCS
  Thanh: 2.3 Streaming fast path → 2.4 Streaming slow path → 2.5 Deploy SimService on VM
  Duy:   2.8 Health panel → test live panels against InfluxDB (once Thanh's fast path writes data)
  Kien:  Slides (help others)

Apr 24 (1 day):
  Duy:   2.9 Deploy updated Streamlit on VM
  ALL:   Integration testing (3.0–3.8) + dress rehearsal + slide finalization

Apr 25 — Demo Day:
  Duy:   Start VM + Cloud SQL, submit Dataproc streaming jobs
  Long:  Lead presentation (opens, closes, runs live demo)
  ALL:   Each presents their section
  Duy:   terraform destroy
```

---

## Demo Day Runbook

> Step-by-step checklist for running the live demo. **Duy** drives infra; **Long** leads the presentation.
> Arrive **30 min early** to warm everything up.

### T-30 min: Warm-up (Duy)

```bash
# 1. Start Cloud SQL + VM (if stopped overnight)
./scripts/infra.sh start
./scripts/infra.sh status          # note the VM external IP

# 2. SSH into VM and verify services are running
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b \
  --command "docker ps"
# Expected: streamlit, model-api, influxdb all running

# 3. Open the dashboard and confirm it loads
#    https://f1.thedblaster.id.vn
#    Check: historical views load, pre-race predictions work
```

### T-20 min: Start Dataproc + Streaming (Duy)

```
Go to GitHub → Actions → "Deploy Dataproc Jobs" → Run workflow → select "all"
```

This will:
- Create the Dataproc cluster (takes ~2–3 min)
- Upload all Spark jobs to GCS
- Submit ETL job (batch — finishes in a few min)
- Submit streaming-fast (async — keeps running)
- Submit streaming-slow (async — keeps running)

**Verify:**
- [ ] GitHub Actions job goes green
- [ ] Check [Dataproc console](https://console.cloud.google.com/dataproc/jobs?project=gen-lang-client-0314607994) — 2 streaming jobs in `RUNNING` state

### T-10 min: Start Simulation (Thanh)

```bash
# SSH into VM and start the simulation service
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b

# On the VM:
cd ~/app
python3 simulation_service.py --speed 5.0 &
# This replays a cached race into Pub/Sub at 5× speed (~18 min)
```

**Verify:**
- [ ] Messages flowing in Pub/Sub (check [Pub/Sub console](https://console.cloud.google.com/cloudpubsub/topic/list?project=gen-lang-client-0314607994) — message rate > 0)
- [ ] InfluxDB receiving data — check dashboard live panels show data within ~10 sec

### T-5 min: Final Check (Duy + Thanh)

- [ ] Dashboard `https://f1.thedblaster.id.vn` loads
- [ ] Historical tab shows data from GCS cache (via FastF1)
- [ ] Live Race Tracker shows moving car positions
- [ ] Live Timing Board shows driver gaps and tyre info
- [ ] Race Control Feed shows flag events
- [ ] Pre-race predictions panel works
- [ ] Health panel shows green status

### Presentation Flow

| Order | Who | Section | Duration |
|-------|-----|---------|----------|
| 1 | **Long** | Opening — project intro, architecture overview | 3 min |
| 2 | **Hieu** | Data pipeline — DataCrawler, GCS, Spark ETL | 3 min |
| 3 | **Kien** | ML models — features, training, accuracy metrics | 4 min |
| 4 | **Thanh** | Streaming — SimService, fast/slow paths, Pub/Sub | 4 min |
| 5 | **Duy** | Live Demo — walk through dashboard, show live panels | 5 min |
| 6 | **Long** | **Key Demo Moment** + closing | 3 min |

### Key Demo Moment (Long drives, Duy assists)

> This is the highlight — shows the decoupled architecture works.

1. **Long narrates:** "Now we'll show what happens when the ML prediction pipeline fails."
2. **Duy** opens the [Dataproc console](https://console.cloud.google.com/dataproc/jobs?project=gen-lang-client-0314607994)
3. **Duy** cancels the **streaming-slow** job (click the job → Cancel)
4. **Long narrates:** "The slow path is down — no more predictions flowing."
5. **Everyone watches the dashboard:**
   - Predictions panel stops updating (shows stale data or "no recent predictions")
   - **Live positions, timing, and race control continue uninterrupted**
6. **Long narrates:** "The fast path is completely independent. Live visualization is unaffected."

### After Demo: Tear Down (Duy)

```bash
# 1. Cancel any remaining Dataproc streaming jobs
#    (or just delete the cluster — kills all jobs)
gcloud dataproc clusters delete f1-chubby-spark \
  --region asia-southeast1 --project gen-lang-client-0314607994 --quiet

# 2. Stop VM + Cloud SQL to save cost
./scripts/infra.sh stop

# 3. (Optional) Full teardown — destroy ALL infrastructure
#    Only do this when the project is completely done:
#    cd infra && terraform destroy
```

---

## Hours Summary

| Person | Remaining Dev | Slides | Total Remaining |
|--------|--------------|--------|-----------------|
| **Hieu** | Flex — assist Thanh | — | **flex** |
| **Long** | 5 hrs (2.1b) | — | **5 hrs** |
| **Thanh** | 21.5 hrs (0.4 + 0.4b + 0.5 + 2.3 + 2.4 + 2.5) | 1 hr | **22.5 hrs** |
| **Duy** | 7 hrs (2.6 + 2.8) | — | **7 hrs** |
| **Kien** | — | 3 hrs | **3 hrs** |
| **Total** | | | **~37.5+ hrs** |

> **Thanh has the heaviest remaining load** (simulation + both streaming paths). Hieu is now freed up to assist Thanh. Kien and Long are also flex capacity if needed.

---

## Local Development & Deployment Guide

### Prerequisites (Everyone)

```bash
# 1. Clone the repo
git clone git@github.com:nmk-k66-uet/F1-Chubby-Data.git && cd F1-Chubby-Data

# 2. Install Docker & Docker Compose (v2)
docker compose version   # must be >= 2.20

# 3. Install gcloud CLI (for GCP deployment)
# https://cloud.google.com/sdk/docs/install

# 4. GCS authentication (for data loading from GCS bucket)
gcloud auth application-default login

# 5. Copy local env file
cp .env.dev.example .env
```

### GCP Resource Reference

| Resource | Value |
|----------|-------|
| **Project ID** | `gen-lang-client-0314607994` |
| **Region / Zone** | `asia-southeast1` / `asia-southeast1-b` |
| **VM** | `f1-chubby-vm` (e2-medium, static IP) |
| **Cloud SQL** | `f1-chubby-postgres` (db-f1-micro, db=`f1chubby`, user=`f1admin`) |
| **GCS Raw Data** | `gs://f1chubby-raw-gen-lang-client-0314607994/` |
| **GCS Models** | `gs://f1chubby-model-gen-lang-client-0314607994/` |
| **GCS Replay** | `gs://f1chubby-replay-gen-lang-client-0314607994/` |
| **GCS Dataproc Staging** | `gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/` |
| **Pub/Sub Topics** | `f1-telemetry`, `f1-timing`, `f1-race-control` |
| **Pub/Sub Subscriptions** | `*-viz-fast`, `*-pred-slow` (6 total) |
| **Dataproc Cluster** | `f1-chubby-spark` (single-node n1-standard-4, auto-delete 10 min idle, **created on-demand by CI**) |
| **InfluxDB** | On VM port 8086 (org=`f1chubby`, bucket=`live_race`) |
| **Domain** | `https://f1.thedblaster.id.vn` (Cloudflare → VM:80) |

### Start/Stop Cloud Resources (save cost)

```bash
./scripts/infra.sh start    # Start Cloud SQL + VM
./scripts/infra.sh stop     # Stop both (saves ~$9/day)
./scripts/infra.sh status   # Check state + IPs
```

---

### Hieu — Assist Thanh with Streaming

#### Local Dev

Hieu's DataCrawler and Spark ETL tasks are completed/presentation-only. Primary focus is now assisting Thanh with the simulation and streaming work. See Thanh's section below for dev instructions.

---

### Long — Spark Model Training

#### Local Dev

```bash
# 1. Work on spark/training_pipeline.py
#    Reference existing training logic in core/ml_core.py
#    Test locally with pyspark:
pip install pyspark scikit-learn joblib

# 2. Test with local data (reads from GCS, writes .pkl locally):
python spark/training_pipeline.py --local \
  --gcs-path gs://f1chubby-raw-gen-lang-client-0314607994/ \
  --output-dir ./assets/Models/

# 3. Verify models were created:
ls -la assets/Models/*.pkl

# 4. Test model loading (sanity check):
python -c "
import joblib
model = joblib.load('assets/Models/podium_model.pkl')
print('Model loaded, features:', model.n_features_in_)
"

# 5. Upload models to GCS manually (for testing):
gsutil cp assets/Models/*.pkl \
  gs://f1chubby-model-gen-lang-client-0314607994/
```

#### Deploy to Dataproc

> **Do NOT run `gcloud dataproc` commands manually.** The cluster is managed by Terraform and jobs are submitted via CI.

1. Push your `spark/training_pipeline.py` to the `main` branch (or your feature branch and merge)
2. Go to **Actions → Deploy Dataproc Jobs → Run workflow**
3. Select **`training`** from the dropdown and click **Run workflow**
4. The CI will ensure the cluster exists, upload your Spark file, and submit the job
5. Monitor the job in the GitHub Actions log or in the [Dataproc console](https://console.cloud.google.com/dataproc/jobs?project=gen-lang-client-0314607994)

---

### Thanh — Simulation + Streaming

#### Local Dev — Simulation Service

```bash
# 1. Install deps
pip install google-cloud-pubsub fastf1

# 2. For local testing without real Pub/Sub, use the emulator:
gcloud components install pubsub-emulator
gcloud beta emulators pubsub-emulator start --project=gen-lang-client-0314607994 &
$(gcloud beta emulators pubsub-emulator env-init)

# 3. Run simulation service locally:
python simulation_service.py --replay-race 2024_bahrain_R --speed 10.0

# 4. Or test against real Pub/Sub (needs GCP auth):
gcloud auth application-default login
python simulation_service.py --replay-race 2024_bahrain_R --speed 10.0
```

#### Local Dev — Pre-Cache Replays

```bash
# Extract race replay to parquet (runs FastF1, writes to replay_cache/)
python scripts/precache_replay.py --race 2024_bahrain_R --output replay_cache/
gsutil -m cp -r replay_cache/ gs://f1chubby-raw-gen-lang-client-0314607994/replay/
```

#### Local Dev — Spark Streaming

```bash
# 1. Start InfluxDB locally
docker compose -f docker-compose.dev.yml up -d influxdb

# 2. Test streaming fast path locally with pyspark:
pip install pyspark influxdb-client google-cloud-pubsub
python spark/streaming_fast.py --local \
  --influxdb-url http://localhost:8086 \
  --influxdb-token f1chubby-influx-token

# 3. In another terminal, run simulation to produce test messages:
python simulation_service.py --replay-race 2024_bahrain_R --speed 50.0

# 4. Verify data in InfluxDB:
curl -s 'http://localhost:8086/api/v2/query?org=f1chubby' \
  -H 'Authorization: Token f1chubby-influx-token' \
  -H 'Content-Type: application/vnd.flux' \
  -d 'from(bucket:"live_race") |> range(start: -1h) |> limit(n:5)'
```

#### Deploy — Simulation on VM

```bash
# SCP the simulation service to the VM
gcloud compute scp simulation_service.py replay_cache/ \
  f1-chubby-vm:~/app/ --zone asia-southeast1-b --recurse

# SSH and run (or add to docker-compose.yml on VM)
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b \
  --command "cd ~/app && python3 simulation_service.py --speed 5.0 &"
```

#### Deploy — Streaming to Dataproc

> **Do NOT run `gcloud dataproc` commands manually.** The cluster is managed by Terraform and jobs are submitted via CI.

1. Push your `spark/streaming_fast.py` and/or `spark/streaming_slow.py` to `main`
2. Go to **Actions → Deploy Dataproc Jobs → Run workflow**
3. Select **`streaming-fast`**, **`streaming-slow`**, or **`all`** from the dropdown
4. The CI will ensure the cluster exists, upload your Spark files, and submit the job(s)
5. Streaming jobs run with `--async` — they keep running on Dataproc until cancelled
6. Monitor in GitHub Actions or the [Dataproc console](https://console.cloud.google.com/dataproc/jobs?project=gen-lang-client-0314607994)

---

### Duy — Streamlit Live Race Panels

#### Local Dev

```bash
# 1. Start the local dev stack (InfluxDB + Model API — no postgres needed for Streamlit)
docker compose -f docker-compose.dev.yml up --build

# 2. Open http://localhost:8501 — Streamlit with hot reload
#    Edit files in components/ and pages/ — changes reflect immediately

# 3. InfluxDB will be empty initially. To test live panels with mock data,
#    write test points directly:
python -c "
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
client = InfluxDBClient(url='http://localhost:8086', token='f1chubby-influx-token', org='f1chubby')
write = client.write_api(write_options=SYNCHRONOUS)
# Write a test live_positions point
write.write('live_race', record=Point('live_positions')
    .tag('driver_id', 'VER')
    .field('x', 1234.5).field('y', 5678.9)
    .field('speed_kph', 312.4).field('gear', 8).field('drs', 1)
    .field('lap_number', 15))
# Write a test live_timing point
write.write('live_race', record=Point('live_timing')
    .tag('driver_id', 'VER')
    .field('position', 1).field('lap_time_ms', 88234)
    .field('gap_to_leader_ms', 0).field('tyre_compound', 'MEDIUM')
    .field('tyre_age_laps', 8))
# Write a test live_race_control point
write.write('live_race', record=Point('live_race_control')
    .tag('scope', 'SECTOR_2')
    .field('flag', 'YELLOW').field('message', 'Yellow flag in sector 2')
    .field('driver_id', 'HAM').field('lap_number', 16))
print('Test data written to InfluxDB')
"

# 4. Existing predictions reader template is at:
#    components/tab_live_race.py line 57 (_fetch_predictions_from_influxdb)

# 5. Check InfluxDB UI at http://localhost:8086 (admin / f1chubby2026)
```

#### Deploy

Streamlit deploys automatically on push to `main` via the **Deploy to VM** workflow.
Files that trigger it: `main.py`, `core/**`, `components/**`, `pages/**`, `assets/**`, `.streamlit/**`.

Manual deploy:
```bash
gcloud compute scp --recurse \
  main.py Dockerfile docker-compose.yml requirements-streamlit.txt \
  .streamlit core components pages model_serving \
  f1-chubby-vm:~/app/ --zone asia-southeast1-b --quiet

gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b \
  --command "cd ~/app && docker compose up -d --build --remove-orphans"
```

---

### Kien — Slides

No local dev or deployment needed. Use Google Slides.

Reference materials for slide content:
- Architecture diagrams: `revised_plan.md` (Mermaid → export via [mermaid.live](https://mermaid.live))
- Model details: `core/ml_core.py` (training logic, features, metrics)
- Model API contract: `model_serving/app.py` (endpoints, request/response schemas)
- Model metrics: `f1_cache/model_metrics.txt`, `f1_cache/in_race_metrics.txt`

---

### Common Workflows

#### Full local stack (for integration testing)

```bash
docker compose -f docker-compose.dev.yml up --build
# influxdb (8086) + model-api (8080) + streamlit (8501)
# postgres (5432) + etl available but optional (for Long's training pipeline only)
```

#### Reset local data

```bash
docker compose -f docker-compose.dev.yml down -v   # removes volumes (PG data, InfluxDB data)
docker compose -f docker-compose.dev.yml up --build # re-seeds from scratch
```

#### View logs

```bash
docker compose -f docker-compose.dev.yml logs -f streamlit   # follow streamlit logs
docker compose -f docker-compose.dev.yml logs -f model-api   # follow model-api logs
docker compose -f docker-compose.dev.yml logs etl            # check ETL seed status
```

#### Connect to Cloud SQL directly

```bash
# Get Cloud SQL IP
./scripts/infra.sh status

# Connect via psql
psql -h <CLOUD_SQL_IP> -U f1admin -d f1chubby
# Password: ask Duy or check Terraform Cloud variables
```

#### SSH to VM

```bash
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b
# App is at ~/app/, docker compose running there
docker ps                           # see running containers
docker compose logs -f streamlit    # follow logs
```
