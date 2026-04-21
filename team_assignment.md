# Team Assignment — F1-Chubby-Data

> **5 members · Updated Apr 21, 2026**
> Focus: remaining pipeline integration work toward Demo Day

---

## Desired Outcome

A working end-to-end demo:

1. **Spark ETL** reads raw data from GCS → populates 4 PostgreSQL tables (race_calendar, session_results, driver_standings, constructor_standings)
2. **Spark Model Training** reads raw data from GCS → engineers features → trains pre-race + in-race models → uploads `.pkl` artifacts to GCS
3. **Simulation Service** replays a cached race into Pub/Sub at 5× speed
4. **Spark Streaming Fast Path** consumes Pub/Sub → writes live_positions, live_timing, live_race_control to InfluxDB (sub-second)
5. **Spark Streaming Slow Path** consumes Pub/Sub → computes windowed features → calls Model Serving API → writes predictions to InfluxDB (5–10 sec)
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
- [x] Streamlit live at `https://f1.thedblaster.id.vn` — historical views from PG with FastF1 fallback
- [x] Pre-race + in-race predictions route through Model Serving API
- [x] GitHub Actions workflows (terraform, deploy-vm, deploy-dataproc, upload-data)
- [x] Streamlit reads `predictions` measurement from InfluxDB (existing reader in `tab_live_race.py`)

### Not Started

- [ ] `spark/etl_pipeline.py` — Spark ETL job (GCS → PG)
- [ ] `spark/training_pipeline.py` — Spark Model Training job (GCS → features → train → .pkl → GCS)
- [ ] `spark/streaming_fast.py` — Spark Streaming fast path (Pub/Sub → InfluxDB live measurements)
- [ ] `spark/streaming_slow.py` — Spark Streaming slow path (Pub/Sub → features → Model API → InfluxDB predictions)
- [ ] Simulation Service — replay cached race into Pub/Sub
- [ ] Pub/Sub message schemas (`/schemas/`)
- [ ] Pre-cached race replays (parquet, 10 Hz interpolated)
- [ ] DataCrawler GCS upload extension
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

### Hieu — DataCrawler → GCS + Spark ETL

#### Task 0.3 — Extend DataCrawler with GCS Upload

| Field | Detail |
|-------|--------|
| **Est. Effort** | 2 hrs |
| **Depends On** | — |
| **Blocks** | 2.1a (Spark ETL reads from GCS) |

Extend `core/data_crawler.py` to upload extracted raw data to GCS after local extraction.

- Add `google-cloud-storage` SDK
- After extraction, upload to `gs://f1chubby-raw/{year}/{round}/{session}/`
- Preserve existing checkpoint/resume logic
- Add `--upload-only` flag for re-uploading existing local data
- Handle GCS upload failures gracefully (retry 3×, log and continue)

#### Task 2.1a — Spark ETL on Dataproc

| Field | Detail |
|-------|--------|
| **Est. Effort** | 5 hrs |
| **Depends On** | 0.3 (data in GCS), 1.3 (PG tables exist) |
| **Blocks** | 3.0 (data quality verify) |

Write `spark/etl_pipeline.py` — reads raw data from GCS, transforms, writes to PostgreSQL.

- Read from `gs://f1chubby-raw/`
- Clean, normalize, resolve schema differences across seasons
- Write to 4 PostgreSQL tables via JDBC: race_calendar, session_results, driver_standings, constructor_standings
- Idempotent: `mode="overwrite"` for re-runs
- Submit: `gcloud dataproc jobs submit pyspark spark/etl_pipeline.py --cluster=<batch-cluster> --jars=postgresql-42.x.jar`

**Done when:**
- [ ] Job completes on Dataproc (exit code 0)
- [ ] All 4 PG tables populated with data for 2018–2026
- [ ] `SELECT COUNT(*) FROM session_results` returns >0 for all covered seasons

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
- Feature Engineering: GridPosition, QualifyingDelta, FP2_PaceDelta, DriverForm, TeamTier (pre-race); lap-by-lap snapshots (in-race)
- Train pre-race RandomForest classifier → `pre_race_model.pkl`
- Train in-race RandomForest regressor → `in_race_model.pkl`, `in_race_podium_model.pkl`
- Upload `.pkl` artifacts to `gs://f1chubby-models/`
- Reference: existing training logic in `core/ml_core.py` (adapt for Spark scale)

**Done when:**
- [ ] Job completes on Dataproc (exit code 0)
- [ ] `gsutil ls gs://f1chubby-models/` shows all model files
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

Extract 2–3 races from FastF1, interpolate to 10 Hz, save as parquet. Upload to `gs://f1chubby-replay/`.

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

## Remaining Timeline (Apr 21 →)

```
Apr 21–23 (3 days):
  Hieu:  0.3 DataCrawler GCS upload → start 2.1a Spark ETL
  Long:  2.1b Spark Model Training pipeline
  Thanh: 0.4 SimService → 0.4b Schemas → 0.5 Replay cache
  Duy:   2.6 Streamlit live race panels (build readers, test with mock/empty data)
  Kien:  Slides (ML section)

Apr 24–26 (3 days):
  Hieu:  Finish 2.1a Spark ETL → verify PG data
  Long:  Finish 2.1b → verify models in GCS
  Thanh: 2.3 Streaming fast path → 2.5 Deploy SimService on VM
  Duy:   2.8 Health panel → test live panels against InfluxDB (once Thanh's fast path writes data)
  Kien:  Slides (help others)

Apr 27–28 (2 days):
  Thanh: 2.4 Streaming slow path (models now in GCS from Long)
  Duy:   2.9 Deploy updated Streamlit on VM
  ALL:   Integration testing (3.0–3.8)

Apr 29:
  ALL:   3.9 Full dress rehearsal + slide finalization

Demo Day:
  Duy:   Start VM + Cloud SQL, submit Dataproc streaming jobs
  Long:  Lead presentation (opens, closes, runs live demo)
  ALL:   Each presents their section
  Duy:   terraform destroy
```

---

## Hours Summary

| Person | Remaining Dev | Slides | Total Remaining |
|--------|--------------|--------|-----------------|
| **Hieu** | 7 hrs (0.3 + 2.1a) | — | **7 hrs** |
| **Long** | 5 hrs (2.1b) | — | **5 hrs** |
| **Thanh** | 21.5 hrs (0.4 + 0.4b + 0.5 + 2.3 + 2.4 + 2.5) | 1 hr | **22.5 hrs** |
| **Duy** | 7 hrs (2.6 + 2.8) | — | **7 hrs** |
| **Kien** | — | 3 hrs | **3 hrs** |
| **Total** | | | **~44.5 hrs** |

> **Thanh has the heaviest remaining load** (simulation + both streaming paths). Kien and Long are flex capacity to help Thanh if needed.
