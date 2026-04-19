# Team Assignment — F1-Chubby-Data

> **5 members, ~89 person-hours total, maximum parallelism**
> Timeline: Apr 19 – Demo Day (Phase 0–4)

---

## Team Overview

| Person | Track | Total Hours | Key Responsibility |
|--------|-------|-------------|-------------------|
| **Duy** | Infrastructure & DevOps | 17 hrs | Terraform, Docker, CI/CD, all deployments |
| **Kien** | ML + Model Serving + DataCrawler | 21 hrs | MLCore.py, Model API, DataCrawler, streaming slow path |
| **Hieu** | Schema + Spark Batch Pipeline | 18 hrs | DB schema, Spark Batch on Dataproc, data quality |
| **Thanh** | Streaming + Simulation | 14.5 hrs | Simulation Service, Pub/Sub schemas, streaming fast path |
| **Long** | Frontend + Presentation Lead | 18.5 hrs | All Streamlit extensions, slide deck owner |

---

## Critical Dependency Chain

```
Hieu 2.1 (Spark Batch, 10h) ──┐
                               ├──→ Kien 2.4 (Streaming slow path)
Duy 2.2 (Deploy Model API) ───┘

Kien 0.2 (MLCore.py) → Kien 0.2b (API contract) → Duy 0.6 (Docker-compose)
Hieu 0.1 (Schema) ────────────────────────────────→ Duy 0.6 (Docker-compose)
Thanh 0.4 (SimService) ───────────────────────────→ Duy 0.6 (Docker-compose)
Duy 0.8 (Terraform) ──→ Duy 1.1–1.5 (Provision) ──→ ALL Phase 2 cloud tasks
```

---

# DUY — Infrastructure & DevOps

**Specialty:** Terraform, cloud infrastructure.
**Owns:** All GCP provisioning, Docker, CI/CD, deployment pipelines. Phase 1 critical path — everyone waits on you.

---

## Task 0.8 — Terraform Configuration

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 3 hrs |
| **Depends On** | — (start immediately) |
| **Blocked By** | Nothing |
| **Blocks** | 1.1–1.5 (all provisioning) |

**Spec:**
Write Terraform config in `infra/` directory that provisions all GCP resources for the project. Use modular structure with separate modules per resource type.

**Requirements:**
- Root module: `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`, `infra/terraform.tfvars`
- Modules in `infra/modules/`:
  - `networking/` — VPC network, firewall rules (allow SSH, HTTP 8501 for Streamlit, 8086 for InfluxDB, 8080 for Model API, internal traffic)
  - `pubsub/` — 3 topics (`f1-telemetry`, `f1-timing`, `f1-race-control`) + 6 subscriptions (`*-viz-fast`, `*-pred-slow`)
  - `storage/` — 3 GCS buckets (`f1chubby-raw`, `f1chubby-models`, `f1chubby-replay`), Standard class, `asia-southeast1`
  - `database/` — Cloud SQL PostgreSQL instance, `db-f1-micro`, activation policy `NEVER` by default (start manually)
  - `compute/` — GCE VM `e2-medium`, startup script installs Docker + docker-compose
  - `dataproc/` — Cluster template configs (single-node `n1-standard-4`, auto-delete)
  - `cloudrun/` — Cloud Run service definition for Streamlit container
- Backend: Terraform Cloud (free tier), workspace `f1-chubby-data`
- Authentication: Workload Identity Federation (OIDC) — no stored GCP service account keys
- All resource names parameterized via `variables.tf`
- Outputs: connection strings, VM IP, Cloud Run URL, Pub/Sub topic names, GCS bucket names

**Definition of Done:**
- [x] `terraform validate` passes with no errors
- [x] `terraform plan` shows all expected resources (Pub/Sub, GCS, Cloud SQL, GCE, Dataproc template, Cloud Run, VPC)
- [x] Variables and outputs are documented
- [x] Terraform Cloud workspace configured with OIDC credentials (both GitHub Actions WIF + Terraform Cloud Dynamic Provider Credentials)
- [x] README in `infra/` explains `terraform apply` and `terraform destroy` usage

---

## Task CI/CD — GitHub Actions Workflows

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 2.5 hrs |
| **Depends On** | 0.8 (Terraform config structure) |
| **Blocks** | — (enhancement, not critical path) |

**Spec:**
Create 5 GitHub Actions workflow files in `.github/workflows/` for automated deployment.

**Requirements:**
1. `terraform.yml` — Runs `terraform plan` on PR, `terraform apply` on merge to `main`. Uses `google-github-actions/auth@v2` with Workload Identity Federation.
2. `deploy-streamlit.yml` — Build Docker image, push to GCR/Artifact Registry, deploy to Cloud Run. Trigger: push to `main` when `Dashboard.py` or `Dockerfile` changes.
3. `deploy-vm.yml` — Build InfluxDB + SimService + Model API Docker images, push to registry, SSH into GCE VM and pull + restart containers. Trigger: manual or push to `main` when relevant files change.
4. `deploy-dataproc.yml` — Upload Spark job files to GCS, submit Dataproc jobs. Trigger: manual.
5. `upload-data.yml` — Upload raw data + replay cache to GCS. Trigger: manual.
- All workflows authenticate via Workload Identity Federation (no service account JSON keys in secrets).

**Definition of Done:**
- [x] All 5 `.yml` files exist in `.github/workflows/`
- [x] Each workflow has correct trigger events
- [x] WIF authentication configured (no stored secrets)
- [x] `terraform.yml` runs `plan` on PR + `apply` on merge
- [x] Workflow syntax validated (`actionlint` or GitHub UI)

---

## Task 0.6 — Docker-Compose for Local Dev

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 2.5 hrs |
| **Depends On** | 0.1 (Schema — InfluxDB bucket names), 0.2b (Model API contract), 0.4 (SimService code) |
| **Blocks** | Local integration testing |

**Spec:**
Create `docker-compose.yml` that runs all VM-hosted services locally for development and testing.

**Requirements:**
- Services:
  - `influxdb` — InfluxDB 2.x, port 8086, auto-create organization `f1chubby` and bucket `f1_live` with 4 measurements
  - `simulation-service` — Build from `SimulationService.py`, connects to Pub/Sub emulator or local mock
  - `model-serving-api` — Build from `model_serving/Dockerfile`, port 8080, loads model from local `model_serving/models/` volume mount
- Environment variables for all connection strings (InfluxDB URL/token, Pub/Sub project, GCS bucket names)
- Health checks for each service
- Shared Docker network

**Definition of Done:**
- [ ] `docker-compose up` starts all 3 services without errors
- [ ] InfluxDB UI accessible at `localhost:8086`
- [ ] Model Serving API responds to `GET http://localhost:8080/health` with `200 OK`
- [ ] Services can communicate with each other over the Docker network

---

## Task 0.7 — Dockerize Streamlit

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 1 hr |
| **Depends On** | — |
| **Blocks** | 2.9 (Cloud Run deploy) |

**Spec:**
Create a `Dockerfile` at the project root that containerizes the Streamlit dashboard.

**Requirements:**
- Base image: `python:3.11-slim`
- Install dependencies from `requirements.txt`
- Copy `Dashboard.py`, `assets/`, and any config files
- Expose port 8501
- `CMD ["streamlit", "run", "Dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]`
- `.dockerignore` excludes `f1_cache/`, `.git/`, `infra/`, `spark/`, `__pycache__/`

**Definition of Done:**
- [x] `docker build -t f1-dashboard .` succeeds (Dockerfile created, no Docker daemon locally to test)
- [ ] `docker run -p 8501:8501 f1-dashboard` starts and the app is accessible at `localhost:8501`
- [ ] Image size is reasonable (<500 MB)

---

## Task 1.1–1.5 — GCP Provisioning

| Field | Detail |
|-------|--------|
| **Phase** | 1 |
| **Est. Effort** | 1.5 hrs total |
| **Depends On** | 0.3 (raw data to upload), 0.5 (replay cache), 0.8 (Terraform config) |
| **Blocks** | ALL Phase 2 cloud tasks |

**Spec:**
Deploy all infrastructure to GCP and verify every resource is operational.

**Requirements (sequential):**
1. **1.1** `terraform apply` — deploy all resources. Upload raw data + replay cache to GCS (`gsutil -m cp`).
2. **1.2** Verify 3 Pub/Sub topics + 6 subscriptions exist (`gcloud pubsub topics list`).
3. **1.3** Start Cloud SQL instance, connect via `psql`, run `sql/init.sql` DDL to create all tables + indexes. Verify with `\dt`.
4. **1.4** SSH to VM, verify Docker is running (startup script), deploy InfluxDB + Model Serving API containers via docker-compose. Initialize InfluxDB buckets. Verify `curl http://<VM_IP>:8080/health` responds.
5. **1.5** Verify Cloud Run service exists and Dataproc API is enabled.

**Definition of Done:**
- [x] `terraform output` shows all connection strings and URLs
- [x] `gcloud pubsub topics list` shows 3 topics (f1-telemetry, f1-timing, f1-race-control)
- [ ] `psql` connects to Cloud SQL and `\dt` shows all 9 tables *(blocked: waiting for Hieu's sql/init.sql)*
- [ ] `curl http://<VM_IP>:8086/health` returns InfluxDB healthy *(blocked: waiting for docker-compose deploy)*
- [ ] `curl http://<VM_IP>:8080/health` returns Model API healthy *(blocked: waiting for Kien's model_serving code)*
- [x] GCS buckets exist (4 buckets verified: raw, models, replay, dataproc-staging)
- [x] Cloud SQL instance running (34.21.160.55, db-f1-micro)
- [x] VM running (34.124.140.104, e2-medium)
- [x] Artifact Registry repo created (f1-chubby, DOCKER)
- [x] Cloud Run + Dataproc APIs enabled

---

## Task 2.2 — Deploy Model Serving API on VM

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 2 hrs |
| **Depends On** | 1.4 (VM ready), 0.2b (API code + Dockerfile) |
| **Blocks** | 2.4 (streaming slow path), 2.8 (health panel) |

**Spec:**
Deploy the Model Serving API container on the GCE VM. Load pre-trained model artifacts from GCS. Verify the `/predict` and `/health` endpoints work.

**Requirements:**
- Pull model artifacts from `gs://f1chubby-models/` to VM local storage
- Start the model-serving-api container with correct environment variables (model path, port 8080)
- Verify `/health` returns `{"status": "healthy", "model_loaded": true, "model_version": "in_race_v1"}`
- Verify `/predict` returns valid predictions for a test payload (use the sample from the interface contract in `revised_plan.md`)
- Configure auto-restart policy (`restart: unless-stopped`)

**Definition of Done:**
- [ ] `curl http://<VM_IP>:8080/health` returns 200 with `model_loaded: true`
- [ ] `curl -X POST http://<VM_IP>:8080/predict -H 'Content-Type: application/json' -d '<test_payload>'` returns predictions with `confidence` and `inference_time_ms`
- [ ] Container auto-restarts after VM reboot
- [ ] Inference latency <500ms for a single-instance request

---

## Task 2.5 — Configure Simulation Service on VM

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 2 hrs |
| **Depends On** | 1.2 (Pub/Sub topics exist), 1.4 (VM ready), 0.4 (SimService code) |
| **Blocks** | 3.2 (Pub/Sub verify) |

**Spec:**
Deploy the Simulation Service container on the GCE VM and configure it to publish to the live GCP Pub/Sub topics.

**Requirements:**
- Start SimulationService container with env vars: `GCP_PROJECT_ID`, `REPLAY_SPEED=5.0`, `REPLAY_RACE=2024_bahrain_R`
- Ensure it reads replay cache from GCS `gs://f1chubby-replay/`
- Verify messages arrive in Pub/Sub (check Cloud Console subscription metrics or `gcloud pubsub subscriptions pull`)
- Configurable start/stop (don't leave running to save Pub/Sub costs)

**Definition of Done:**
- [ ] Start the service → messages appear in all 3 Pub/Sub topics within 5 seconds
- [ ] Stop the service → publishing stops cleanly (no orphan processes)
- [ ] Messages match the schemas defined in `/schemas/`
- [ ] Replay speed is configurable via environment variable

---

## Task 2.9 — Deploy Streamlit to Cloud Run

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 1 hr |
| **Depends On** | 2.6, 2.7, 2.8 (all Streamlit work done) |
| **Blocks** | 3.5, 3.6 (verification) |

**Spec:**
Build and deploy the Streamlit Docker image to Cloud Run.

**Requirements:**
- Build image, push to Artifact Registry (`gcloud builds submit` or `docker push`)
- Deploy to Cloud Run with environment variables for Cloud SQL connection string, InfluxDB URL/token, Model API URL
- Set min-instances=0 (scale to zero), max-instances=2
- Allow unauthenticated access (for demo)
- Set Cloud SQL connection via Cloud Run's built-in Cloud SQL proxy

**Definition of Done:**
- [ ] Cloud Run URL serves the Streamlit dashboard
- [ ] Dashboard loads without errors (no broken DB connections)
- [ ] Scales to zero when no traffic (verify in Cloud Console after ~15 min idle)
- [ ] All environment variables correctly configured

---

## Task 3.2 — Verify Pub/Sub Events

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 30 min |
| **Depends On** | 2.5 |

**Spec:** Start Simulation Service → verify messages arrive in all 3 Pub/Sub topics via Cloud Console metrics.

**Definition of Done:**
- [ ] Message count metrics increase on all 3 topics
- [ ] Pull a sample message from each subscription and validate against `/schemas/`

---

## Task 3.8 — Verify Pipeline Health Panel

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 30 min |
| **Depends On** | 2.8, 3.3, 3.4 |

**Spec:** With all pipeline components running, verify the health panel in the dashboard shows correct status for every component.

**Definition of Done:**
- [ ] Pub/Sub backlog shown (numbers match Cloud Console)
- [ ] Last-write timestamps for InfluxDB and PostgreSQL shown and recent
- [ ] Dataproc job status correctly displayed
- [ ] Model API `/health` status shown (healthy, model version, latency)
- [ ] Data quality summary shown

---

# KIEN — ML + Model Serving + DataCrawler

**Context:** Built `Dashboard.py` and `DataCrawler.py`. Currently handling the ML component. Knows the F1 domain and data model best.
**Owns:** Both ML models, Model Serving API implementation, DataCrawler extension, streaming slow path.

---

## Task 0.2 — Implement MLCore.py

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 5 hrs |
| **Depends On** | — (start immediately) |
| **Blocks** | 0.2b (API contract), 0.6 (Docker-compose) |

**Spec:**
Create `MLCore.py` with two scikit-learn RandomForest models: a pre-race podium classifier and an in-race position predictor. Include training scripts and a serialized prediction interface.

**Requirements:**
- **Pre-Race Model (podium classifier):**
  - Features: `GridPosition`, `QualifyingDelta`, `FP2_PaceDelta`, `DriverForm`, `TeamTier` (from `DataCrawler.py` feature engineering)
  - Target: Binary — top 3 finish (podium = 1, else = 0)
  - Algorithm: `sklearn.ensemble.RandomForestClassifier`
  - Output: `pre_race_model.pkl` (joblib serialized)
  - Evaluation: accuracy, precision, recall on held-out test set (print to stdout)
- **In-Race Model (position predictor):**
  - Features: `CurrentPosition`, `GapToLeader`, `TyreCompound`, `TyreAge`, `PitStopsMade`, `SafetyCarActive`, `LapsRemaining`
  - Target: Predicted finishing position (integer 1–20)
  - Algorithm: `sklearn.ensemble.RandomForestRegressor`
  - Training data: Historical in-race snapshots — lap-by-lap state → final result (construct from existing data)
  - Output: `in_race_model.pkl` (joblib serialized)
  - Evaluation: MAE, RMSE on held-out test set
- Both models must have a `predict(features_dict) → result` function callable from the serving API
- Save trained artifacts to `model_serving/models/`

**Definition of Done:**
- [ ] `MLCore.py` exists and runs without errors: `python MLCore.py`
- [ ] Training completes on existing `f1_cache/historical_data_v2.csv` data
- [ ] `pre_race_model.pkl` and `in_race_model.pkl` are created in `model_serving/models/`
- [ ] Pre-race model accuracy >50% (better than random for 3/20 = 15% base rate)
- [ ] In-race model MAE <3 positions
- [ ] Both models are loadable via `joblib.load()` and callable with a dict of features

---

## Task 0.2b — Model Serving API Contract + Implementation

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 3 hrs |
| **Depends On** | 0.2 (models exist to serve) |
| **Blocks** | 0.6 (Docker-compose), 2.2 (deploy on VM), 2.4 (slow path calls it) |

**Spec:**
Define the REST API contract and implement the Model Serving API in `model_serving/`. This is the decoupled inference endpoint that the Spark Streaming slow path will call.

**Requirements:**
- **Directory structure:**
  - `model_serving/Dockerfile`
  - `model_serving/app.py` — REST API implementation
  - `model_serving/models/` — model artifacts (`.joblib` files)
  - `model_serving/requirements.txt`
- **Endpoints:**
  - `POST /predict` — Accept JSON body with `instances` array (see interface contract in `revised_plan.md`). Load the in-race model, run inference, return `predictions` array with `driver_id`, `predicted_position`, `confidence`.
  - `GET /health` — Return `{"status": "healthy", "model_loaded": true, "model_version": "in_race_v1", "uptime_seconds": N}`
- **Error handling:**
  - Invalid JSON → 400 with error message
  - Missing required fields → 400 with field list
  - Model not loaded → 503 with `model_loaded: false`
- **Response includes:** `model_version` and `inference_time_ms` for monitoring
- **Technology choice:** FastAPI + joblib recommended (simplest), but team may choose MLflow or BentoML — the contract must remain the same
- **Dockerfile:** Multi-stage build, expose port 8080

**Definition of Done:**
- [ ] `docker build -t model-api model_serving/` succeeds
- [ ] `docker run -p 8080:8080 model-api` starts successfully
- [ ] `GET /health` returns 200 with `model_loaded: true`
- [ ] `POST /predict` with valid payload returns predictions with correct schema
- [ ] `POST /predict` with invalid payload returns 400
- [ ] Inference time <500ms for 20-driver batch (single race)
- [ ] Contract matches the interface spec in `revised_plan.md`

---

## Task 0.3 — Extend DataCrawler with GCS Upload

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 2 hrs |
| **Depends On** | — (Kien owns this code) |
| **Blocks** | 1.1 (data upload) |

**Spec:**
Extend the existing `DataCrawler.py` to upload extracted raw data to Google Cloud Storage after local extraction.

**Requirements:**
- Add `google-cloud-storage` SDK dependency to `requirements.txt`
- After each session's data is extracted and saved locally, upload to GCS: `gs://f1chubby-raw/{year}/{round}/{session}/`
- Preserve the existing resumable crawling / checkpoint logic
- Validate coverage: 2018–2025 for results/standings, 2019–2025 for telemetry
- Handle GCS upload failures gracefully (retry 3×, log and continue)
- Add a `--upload-only` flag to re-upload existing local data without re-extracting

**Definition of Done:**
- [ ] `python DataCrawler.py` extracts data AND uploads to GCS (when `GOOGLE_APPLICATION_CREDENTIALS` is set)
- [ ] GCS bucket contains files partitioned as `{year}/{round}/{session}/`
- [ ] `--upload-only` flag works for re-uploading existing data
- [ ] Upload failures are logged but don't crash the crawler
- [ ] Existing local CSV output still works unchanged

---

## Task — Brief Long on Dashboard.py

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Day 1–2) |
| **Est. Effort** | 30 min |
| **Depends On** | — |
| **Blocks** | Long's 2.6, 2.7, 2.8 work |

**Spec:**
Walk Long through the `Dashboard.py` codebase so he can extend it for live panels and PostgreSQL queries.

**Requirements:**
- Explain: page structure, tab system, FastF1 data loading, session state management
- Point out: where to add new pages/tabs for live views, how existing cache logic works
- Clarify: which views should keep FastF1 cache (replay, dominance, gear maps) vs. migrate to PostgreSQL

**Definition of Done:**
- [ ] Long can navigate `Dashboard.py` and explain the page structure
- [ ] Long knows where to add new tabs and how `st.session_state` is used

---

## Task 2.4 — Spark Streaming Slow Path

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 7 hrs |
| **Depends On** | 1.2 (Pub/Sub exists), 1.4 (VM + InfluxDB ready), 2.1 (batch done = trained models in GCS), 2.2 (Model API deployed) |
| **Blocks** | 2.8 (health panel), 3.4 (verify), 3.7 (kill test) |

**Spec:**
Write `spark/streaming_slow.py` — a PySpark Structured Streaming job that consumes from Pub/Sub, computes windowed features, calls the Model Serving API for inference, and writes predictions to InfluxDB.

**Requirements:**
- **Input:** Pub/Sub subscriptions `f1-telemetry-pred-slow`, `f1-timing-pred-slow`, `f1-race-control-pred-slow`
- **Processing:**
  1. Parse JSON messages, validate against schemas in `/schemas/`
  2. Window: 5–10 second tumbling windows
  3. Compute features per driver within window: `CurrentPosition`, `GapToLeader`, `TyreCompound`, `TyreAge`, `PitStopsMade`, `SafetyCarActive`, `LapsRemaining`
  4. For each window, batch all drivers' features → `POST http://<MODEL_API_IP>:8080/predict` with `{"instances": [...]}`
  5. Parse response, extract `predicted_position` and `confidence` per driver
- **Output:** Write to InfluxDB `predictions` measurement:
  - Tags: `driver_id`
  - Fields: `predicted_position` (int), `confidence` (float), `model_version` (string), `inference_time_ms` (int)
  - Timestamp: window end time
- **Error handling:** If Model API returns non-200, log the error and skip the window (don't crash the job). Write a "prediction_unavailable" marker to InfluxDB.
- **Platform:** Dataproc single-node cluster, submitted via `gcloud dataproc jobs submit pyspark`
- **Libraries:** `pyspark`, `google-cloud-pubsub`, `influxdb-client`, `requests`

**Definition of Done:**
- [ ] `streaming_slow.py` submitted to Dataproc and running without errors
- [ ] With Simulation Service publishing, predictions appear in InfluxDB `predictions` measurement within 10 seconds
- [ ] Each prediction has `driver_id`, `predicted_position`, `confidence`, `model_version`
- [ ] Model API failure → graceful degradation (job continues, writes "unavailable" marker)
- [ ] **Kill this job → fast path (live viz) continues unaffected** (key demo test)

---

## Task 3.4 — Verify Slow-Path Predictions

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 1 hr |
| **Depends On** | 2.4, 3.2 |

**Spec:** Verify predictions appear in InfluxDB and are displayed in the Streamlit AI Predictions panel.

**Definition of Done:**
- [ ] Query InfluxDB `predictions` → data exists with recent timestamps
- [ ] Predictions update every 5–10 seconds during simulation
- [ ] Streamlit AI Predictions panel shows driver predictions with staleness indicator

---

## Task 3.7 — Kill Slow-Path Demo Test

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 15 min |
| **Depends On** | 3.6 |

**Spec:** **The key demo moment.** Kill the slow-path streaming job and confirm live visualization continues uninterrupted.

**Definition of Done:**
- [ ] Stop the slow-path Dataproc job
- [ ] Live race tracker, timing board, race control feed continue updating in real time
- [ ] AI predictions panel shows stale warning (>15 sec) but doesn't crash
- [ ] Re-start slow path → predictions resume

---

## Slides — ML & Model Serving (2–3 slides)

| Field | Detail |
|-------|--------|
| **Phase** | Use gap in Phase 2 Day 1-2 (blocked on 2.1+2.2) |
| **Est. Effort** | 1.5 hrs |
| **Presenter** | Kien (~4 min) |

**Slide content:**
1. Two ML models: features, algorithms, training approach, accuracy metrics
2. Model Serving API: interface contract, decoupled architecture, hot-swap capability
3. Streaming slow path: feature windowing → API call → InfluxDB predictions

---

# HIEU — Schema Design + Spark Batch Pipeline

**Owns:** Database schema design, the Spark Batch job (biggest single task: 10 hrs), data quality validation.

---

## Task 0.1 — Database Schema Design

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 4 hrs |
| **Depends On** | — (start immediately) |
| **Blocks** | 0.6 (Docker-compose needs InfluxDB bucket names), 1.3 (Cloud SQL DDL), 2.1 (Spark writes to these tables) |

**Spec:**
Design the full database schema for both PostgreSQL (historical) and InfluxDB (live). Write DDL scripts.

**Requirements:**
- **PostgreSQL — `sql/init.sql`:**
  - 9 tables: `race_calendar`, `session_results`, `driver_standings`, `constructor_standings`, `lap_times`, `telemetry_summary`, `ml_features`, `prediction_accuracy`, `data_quality`
  - All tables: explicit column types (INT, VARCHAR, FLOAT, TIMESTAMP, BOOLEAN), NOT NULL constraints where appropriate
  - Primary keys on every table (composite where needed, e.g., `(year, round, driver_id, lap_number)` for `lap_times`)
  - Foreign keys: `session_results.driver_id` → driver reference, etc.
  - Indexes: covering indexes for common dashboard queries (e.g., `CREATE INDEX idx_lap_times_session ON lap_times(year, round, session_type)`)
  - Include `INSERT` test data for 1 race (for local testing)
- **InfluxDB — document in a `schemas/influxdb_schema.md`:**
  - Bucket: `f1_live`
  - 4 measurements: `live_positions`, `live_timing`, `live_race_control`, `predictions`
  - For each: tags (indexed string fields), fields (values), timestamp semantics
  - Retention policy: 7 days

**Definition of Done:**
- [ ] `sql/init.sql` runs without errors on a fresh PostgreSQL database
- [ ] All 9 tables created with correct columns, types, PKs, FKs, and indexes
- [ ] `\dt` shows all tables, `\d <table>` shows correct schema
- [ ] InfluxDB schema document exists and specifies all 4 measurements with tags/fields
- [ ] Test data inserts successfully

---

## Task 2.1 — Spark Batch Job on Dataproc

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 10 hrs |
| **Depends On** | 1.1 (GCS data uploaded), 1.3 (Cloud SQL tables exist), 1.5 (Dataproc API enabled), 0.2 (MLCore.py for model training) |
| **Blocks** | 2.4 (trained models needed), 2.7 (historical data in PostgreSQL), 3.0, 3.1 |

**Spec:**
Write `spark/batch_pipeline.py` — a PySpark batch job that reads raw data from GCS, transforms it, engineers ML features, trains models, and loads everything into Cloud SQL PostgreSQL.

**Requirements:**
- **Sub-jobs (in order):**
  1. **Data Load + Transform:** Read all raw session data from `gs://f1chubby-raw/`. Clean, normalize column names, handle missing values, resolve schema differences across F1 seasons (column renames, format changes).
  2. **Feature Engineering:** Compute: `GridPosition`, `QualifyingDelta` (Q time - pole time), `FP2_PaceDelta`, `DriverForm` (rolling average of last 5 races), `TeamTier` (constructor standing group).
  3. **Model Training:** Import `MLCore.py` training functions. Train both models on full dataset. Save artifacts to `gs://f1chubby-models/`.
  4. **PostgreSQL Load:** Write all 8 data tables to Cloud SQL via JDBC (`org.postgresql.Driver`). Use `mode="overwrite"` for idempotent re-runs.
  5. **Data Quality Validation:** For each table and each season: count rows, compare against expected counts. Write summary to `data_quality` table. Flag anomalies (0 rows for a season = error).
- **JDBC connection:** Use Cloud SQL private IP (within VPC) or Cloud SQL Proxy.
- **Submit via:** `gcloud dataproc jobs submit pyspark spark/batch_pipeline.py --cluster=<batch-cluster> --jars=postgresql-42.x.jar`

**Definition of Done:**
- [ ] Job completes successfully on Dataproc (exit code 0)
- [ ] All 9 PostgreSQL tables populated: `SELECT COUNT(*) FROM <table>` > 0 for all tables
- [ ] `race_calendar` has entries for 2018–2025
- [ ] `session_results` has all sessions for all covered seasons
- [ ] `ml_features` has engineered features with no NULL values in required columns
- [ ] Model artifacts exist in `gs://f1chubby-models/`: `pre_race_model.pkl`, `in_race_model.pkl`
- [ ] `data_quality` table has row-count summaries per season per table
- [ ] Job is idempotent: re-running produces the same result (overwrite mode)

---

## Task 3.0 — Data Quality Validation

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 2 hrs |
| **Depends On** | 2.1 |

**Spec:** Verify batch-processed data integrity across all tables and seasons.

**Definition of Done:**
- [ ] No season has 0 rows in any table (all seasons 2018–2025 represented)
- [ ] `lap_times` rows per race ≈ laps × drivers (sanity check)
- [ ] No orphan foreign keys
- [ ] `data_quality` table confirms all checks passed

---

## Task 3.1 — Batch End-to-End Verify

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 1 hr |
| **Depends On** | 2.1 |

**Spec:** Manually query PostgreSQL for known results (e.g., "Who won the 2024 Bahrain GP?") and verify model artifacts load correctly.

**Definition of Done:**
- [ ] Query `session_results WHERE year=2024 AND round=1 ORDER BY position LIMIT 3` returns the correct podium
- [ ] `gsutil ls gs://f1chubby-models/` shows both model files
- [ ] `joblib.load('pre_race_model.pkl')` works and can predict

---

## Slides — Data Pipeline & Batch Processing (2 slides)

| Field | Detail |
|-------|--------|
| **Phase** | Use buffer time in Phase 0 Day 3-5 or Phase 2 gaps |
| **Est. Effort** | 1 hr |
| **Presenter** | Hieu (~3 min) |

**Slide content:**
1. Batch pipeline: GCS → Transform → Feature Engineering → PostgreSQL (diagram from plan)
2. Data quality: validation approach, coverage statistics, table schema overview

---

# THANH — Streaming + Simulation

**Owns:** Simulation Service, Pub/Sub message schemas, streaming fast path.

---

## Task 0.4 — Build Simulation Service

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 4 hrs |
| **Depends On** | — (start immediately) |
| **Blocks** | 0.5 (pre-cache), 0.6 (Docker-compose), 2.5 (VM deploy) |

**Spec:**
Create `SimulationService.py` — reads a pre-cached historical race from GCS (or local file) and replays it to Pub/Sub at configurable speed, simulating a live race feed.

**Requirements:**
- Read race data from GCS `gs://f1chubby-replay/{race_id}/` or local path (for testing)
- Data format: parquet files with all cars interpolated to unified 10 Hz timeline
- Publish to 3 Pub/Sub topics using `google-cloud-pubsub` `PublisherClient`:
  - `f1-telemetry`: ~10 Hz per car (20 cars = ~200 msg/sec at 1× speed)
  - `f1-timing`: per lap per car (event-driven)
  - `f1-race-control`: flags and incidents (event-driven)
- Speed control: `REPLAY_SPEED` env var (default `5.0`). At 5×, a ~90 min race replays in ~18 min.
- Graceful shutdown on SIGTERM (flush pending messages)
- JSON message format must match schemas in `/schemas/`
- Log: current lap number, elapsed time, messages published per second

**Definition of Done:**
- [ ] `python SimulationService.py` runs locally (with Pub/Sub emulator or mock)
- [ ] At `REPLAY_SPEED=5.0`, a full race completes in ~18 min
- [ ] All 3 topics receive messages at the expected rates
- [ ] Messages validate against `/schemas/*.json`
- [ ] SIGTERM → clean shutdown within 2 seconds
- [ ] Configurable via env vars: `REPLAY_SPEED`, `REPLAY_RACE`, `GCS_BUCKET` (or `LOCAL_PATH`)

---

## Task 0.4b — Pub/Sub Message Schemas

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 1.5 hrs |
| **Depends On** | — |
| **Blocks** | 2.3 (fast path parses these), 2.4 (slow path parses these) |

**Spec:**
Define JSON Schema documents for all 3 Pub/Sub topic message types.

**Requirements:**
- Files: `schemas/f1-telemetry.json`, `schemas/f1-timing.json`, `schemas/f1-race-control.json`
- JSON Schema draft-07 format
- All fields: type, required/optional, description, valid ranges (e.g., `gear: 0-8`, `speed_kph: 0-400`)
- Match the examples in `revised_plan.md` Message Schemas section exactly
- Include a `schemas/validate.py` utility script that can validate a message against its schema

**Definition of Done:**
- [ ] 3 JSON Schema files exist in `/schemas/`
- [ ] `python schemas/validate.py f1-telemetry '{"timestamp_ms":..., "driver_id":"VER", ...}'` returns valid
- [ ] Invalid messages (missing fields, wrong types) are rejected with descriptive errors
- [ ] Schemas match the message examples in `revised_plan.md`

---

## Task 0.5 — Pre-Cache Race Replays

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) |
| **Est. Effort** | 1 hr |
| **Depends On** | 0.4 (SimService needs this format) |
| **Blocks** | 1.1 (upload to GCS) |

**Spec:**
Create a one-time script that extracts 2–3 full race sessions from FastF1, interpolates all cars to a unified 10 Hz timeline, and saves as parquet files for the Simulation Service.

**Requirements:**
- Extract at least: 2024 Bahrain GP (Race), 1 additional race of choice
- Interpolate all 20 cars to unified 10 Hz timeline (100ms intervals)
- Output format: parquet files, one per topic type (telemetry, timing, race_control)
- Partition: `replay-cache/{race_id}/telemetry.parquet`, `timing.parquet`, `race_control.parquet`
- Include a README in `replay-cache/` explaining the format

**Definition of Done:**
- [ ] Parquet files exist for at least 2 races
- [ ] `SimulationService.py` can read and replay them without errors
- [ ] Telemetry data has continuous 10 Hz timestamps for all 20 cars
- [ ] Timing data has all lap completions
- [ ] Total file size <500 MB

---

## Task 2.3 — Spark Streaming Fast Path

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 6 hrs |
| **Depends On** | 1.2 (Pub/Sub exists), 1.4 (InfluxDB ready), 1.5 (Dataproc API), 0.4b (schemas) |
| **Blocks** | 3.3 (verify), 3.6 (live views) |

**Spec:**
Write `spark/streaming_fast.py` — a PySpark Structured Streaming job that consumes from Pub/Sub, validates/enriches messages, and writes to InfluxDB with sub-second latency. **No ML dependency.**

**Requirements:**
- **Input:** Pub/Sub subscriptions `f1-telemetry-viz-fast`, `f1-timing-viz-fast`, `f1-race-control-viz-fast`
- **Processing per message:**
  1. Parse JSON, validate required fields against schemas
  2. Enrich: add driver full name, team name, car number (broadcast lookup table)
  3. Convert `timestamp_ms` to InfluxDB-compatible timestamp
- **Output:** Write to InfluxDB bucket `f1_live`:
  - `live_positions`: tags=`driver_id`, fields=`x`, `y`, `speed_kph`, `gear`, `drs`, `lap_number`
  - `live_timing`: tags=`driver_id`, fields=`position`, `lap_time_ms`, `gap_to_leader_ms`, `tyre_compound`, `tyre_age_laps`
  - `live_race_control`: tags=`scope`, fields=`flag`, `message`, `driver_id`, `lap_number`
- **Latency:** Sub-second end-to-end (Pub/Sub → InfluxDB). Use micro-batch trigger `processingTime="500ms"`.
- **Failure isolation:** This job is independent of the slow path. If this crashes, predictions are unaffected.
- **Platform:** Dataproc single-node cluster, `--max-idle=10m` for auto-shutdown
- **Libraries:** `pyspark`, `google-cloud-pubsub`, `influxdb-client`

**Definition of Done:**
- [ ] Job submitted to Dataproc and running without errors
- [ ] With Simulation Service publishing: data appears in InfluxDB within 1 second
- [ ] `live_positions` has X/Y coordinates updating in real time for all 20 cars
- [ ] `live_timing` has lap times updating per lap completion
- [ ] `live_race_control` shows flag events
- [ ] Invalid messages are logged and skipped (don't crash the job)
- [ ] This job runs independently — unaffected by slow path status

---

## Task 3.3 — Verify Fast-Path Live Data

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 1 hr |
| **Depends On** | 2.3, 3.2 |

**Spec:** Verify live data flows from Simulation → Pub/Sub → Spark Fast Path → InfluxDB within 1 second.

**Definition of Done:**
- [ ] Query InfluxDB `live_positions` → data for all 20 cars with recent timestamps
- [ ] Latency: message timestamp to InfluxDB write < 1 second
- [ ] Data refreshes at ~10 Hz for telemetry

---

## Slides — Streaming & Simulation (2 slides)

| Field | Detail |
|-------|--------|
| **Phase** | Use buffer time in Phase 0 Day 4-5 or Phase 1 |
| **Est. Effort** | 1 hr |
| **Presenter** | Thanh (~3 min) |

**Slide content:**
1. Streaming architecture: fast/slow path separation, backpressure isolation, why two jobs
2. Simulation Service: how replay works, speed control, message flow

> **Thanh has lightest load (~14.5 hrs).** Flex capacity to help Hieu with 2.1 Spark Batch subtasks, Long with Streamlit, or slides.

---

# LONG — Frontend (Streamlit) + Presentation Lead

**Owns:** All Streamlit dashboard extensions (live panels, PostgreSQL queries, health panel). Leads slide deck creation. Gets briefed by Kien on existing `Dashboard.py`.

---

## Task — Slide Deck Structure (Phase 0)

| Field | Detail |
|-------|--------|
| **Phase** | 0 (Local Preparation) — start Day 1 |
| **Est. Effort** | 3 hrs |
| **Depends On** | — (no code dependencies, can start immediately) |
| **Blocks** | — |

**Spec:**
Create the Google Slides deck with structure, design template, and architecture diagrams (export from Mermaid in `revised_plan.md`).

**Requirements:**
- Google Slides, shared with all 5 team members
- ~18–20 slide placeholders with section titles
- Design template: dark theme (matches F1 aesthetics), consistent fonts, team logo
- Export Mermaid diagrams as images (use mermaid.live or similar) for:
  - High-level architecture
  - Batch processing flow
  - Streaming processing flow
  - Dual-database strategy
- Leave placeholder slides for each team member's section
- Slide structure:

  | # | Section | Slides | Presenter |
  |---|---------|--------|-----------|
  | 1 | Title + team intro | 1 | Long |
  | 2 | Problem statement & motivation | 1-2 | Long |
  | 3 | Architecture overview | 3 | Long |
  | 4 | Tech stack & infra justification | 2 | Duy |
  | 5 | Data pipeline: batch | 2 | Hieu |
  | 6 | Streaming: fast + slow paths | 2 | Thanh |
  | 7 | ML & Model Serving API | 2-3 | Kien |
  | 8 | Dashboard demo | 3-4 | Long |
  | 9 | Design decisions & lessons learned | 1-2 | Long |
  | 10 | Q&A | 1 | All |

**Definition of Done:**
- [ ] Google Slides deck created and shared with all team members (edit access)
- [ ] All section placeholders exist with titles
- [ ] Architecture diagrams exported and placed
- [ ] Design template applied (dark theme, consistent styling)

---

## Task 2.6 — Streamlit Live Race Panels

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 5 hrs |
| **Depends On** | 0.1 (InfluxDB measurement schema), Kien's brief on Dashboard.py |
| **Blocks** | 2.9 (deploy), 3.6 (verify) |

**Spec:**
Add 4 new live race views to `Dashboard.py` that query InfluxDB for real-time data.

**Requirements:**
- **Live Race Tracker:** Map/track visualization showing car positions (X/Y from `live_positions`). Auto-refresh every 1 second.
- **Live Timing Board:** Table showing all drivers: position, gap to leader, interval, last lap time, tyre compound. Query `live_timing`. Auto-refresh.
- **Race Control Feed:** Scrollable feed of flag events, safety car, incidents. Query `live_race_control`. Auto-refresh.
- **AI Predictions Panel:** Table showing predicted finishing positions per driver with confidence scores. Query `predictions`.
  - **Staleness indicator:** Show timestamp of last prediction. If >15 seconds stale, show warning badge (yellow). If >30 seconds, show error badge (red).
- All views use `influxdb-client` Python SDK
- Add `INFLUXDB_URL` and `INFLUXDB_TOKEN` to environment variable config
- New views should be in separate tabs/pages consistent with existing UI structure

**Definition of Done:**
- [ ] 4 new views visible in the Streamlit app
- [ ] Live Race Tracker shows car positions on a track layout (or grid)
- [ ] Live Timing Board auto-refreshes and shows all 20 drivers with correct data
- [ ] Race Control Feed shows flag events as they happen
- [ ] AI Predictions panel shows predictions with staleness indicator
- [ ] Staleness: >15s → yellow badge, >30s → red badge
- [ ] All views handle "no data" gracefully (show "Waiting for data..." instead of errors)

---

## Task 2.7 — Streamlit PostgreSQL Query Layer

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 4 hrs |
| **Depends On** | 1.3 (Cloud SQL tables), 2.1 (data loaded) |
| **Blocks** | 2.9 (deploy), 3.5 (verify) |

**Spec:**
Add Cloud SQL PostgreSQL as a data source for the existing historical views in `Dashboard.py`.

**Requirements:**
- Add `psycopg2-binary` (or `SQLAlchemy`) to dependencies
- Connection via environment variables: `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DATABASE`
- Migrate these views to query PostgreSQL instead of (or alongside) FastF1 cache:
  - Calendar page → `SELECT * FROM race_calendar`
  - Results tab → `SELECT * FROM session_results WHERE year=? AND round=?`
  - Standings → `SELECT * FROM driver_standings WHERE year=?`
  - Lap times chart → `SELECT * FROM lap_times WHERE year=? AND round=? AND session_type=?`
  - Telemetry comparison → `SELECT * FROM telemetry_summary` + fallback to FastF1 cache for full-res
- **Keep FastF1 cache** for: Race Replay, Track Dominance, Gear Maps (these need 100ms X/Y and per-meter Distance — too granular for SQL)
- Use `@st.cache_data` with TTL for expensive queries
- Add connection error handling: if PostgreSQL is down, fall back to FastF1 cache and show warning

**Definition of Done:**
- [ ] Historical views load data from Cloud SQL PostgreSQL
- [ ] Calendar, Results, Standings, Lap Times work with SQL queries
- [ ] Telemetry comparison queries PostgreSQL with FastF1 fallback
- [ ] Race Replay, Track Dominance, Gear Maps still use FastF1 cache
- [ ] PostgreSQL down → views fall back to FastF1 cache with warning banner
- [ ] Query performance: page load <3 seconds for any view

---

## Task 2.8 — Pipeline Health Panel

| Field | Detail |
|-------|--------|
| **Phase** | 2 (Pipeline Integration) |
| **Est. Effort** | 3 hrs |
| **Depends On** | 2.1 (batch data), 2.2 (Model API), 2.4 (slow path) |
| **Blocks** | 2.9 (deploy), 3.8 (verify) |

**Spec:**
Add a Pipeline Health panel/page to the Streamlit dashboard showing operational status of all system components.

**Requirements:**
- **Pub/Sub Subscription Backlog:** Query Cloud Monitoring API (or `gcloud pubsub subscriptions describe`) for unacked message count per subscription. Show green/yellow/red status.
- **Database Freshness:** Query last-write timestamp per InfluxDB measurement and PostgreSQL table. Show time-since-last-write. >5 min → yellow, >15 min → red.
- **Dataproc Job Status:** Query Dataproc REST API (`gcloud dataproc jobs list`) for running streaming jobs. Show RUNNING/FAILED/STOPPED.
- **Model Serving API Health:** `GET http://<VM_IP>:8080/health` → show model version, loaded status, inference latency.
- **Data Quality Summary:** Query `data_quality` table from PostgreSQL → show row counts per season, flag any anomalies.
- Auto-refresh every 30 seconds.

**Definition of Done:**
- [ ] Health panel exists as a page/tab in the dashboard
- [ ] Shows all 5 categories: Pub/Sub, DB freshness, Dataproc, Model API, Data Quality
- [ ] Green/yellow/red indicators work correctly
- [ ] Auto-refreshes every 30 seconds
- [ ] Handles individual component failures gracefully (show "unreachable" instead of crashing)

---

## Task 3.5 — Verify Historical Views

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 30 min |
| **Depends On** | 2.7, 3.1 |

**Definition of Done:**
- [ ] Calendar page shows all seasons 2018–2025
- [ ] Results page shows correct race winners
- [ ] Standings page matches official F1 standings
- [ ] Lap times chart renders without errors

---

## Task 3.6 — Verify Live Views

| Field | Detail |
|-------|--------|
| **Phase** | 3 (Testing) |
| **Est. Effort** | 1 hr |
| **Depends On** | 3.3, 3.4 |

**Definition of Done:**
- [ ] Live tracker updates in real time (all 20 cars visible)
- [ ] Timing board matches Simulation Service output
- [ ] Race control feed shows flag events
- [ ] AI Predictions update every 5–10 seconds with staleness indicator
- [ ] Fast path views continue when slow path is stopped

---

## Slides — Demo Walkthrough + Assembly (Presentation Lead)

| Field | Detail |
|-------|--------|
| **Phase** | Phase 3 (finalize) |
| **Est. Effort** | 2 hrs (assembly) + 3 hrs (Phase 0 structure) = 5 hrs total |
| **Presenter** | Long opens (~7 min) and closes (~2 min). Runs live demo (~6 min). |

**Responsibilities:**
- Create slide structure and design template (Phase 0)
- Export architecture diagrams from Mermaid → images (Phase 0)
- Collect each member's section slides and ensure consistent styling
- Create demo walkthrough section: screenshots or live demo script with talking points
- Write the "Key Design Decisions & Lessons Learned" section (with all team input)
- Finalize transitions and rehearsal script
- Lead the 30-min presentation and manage slide transitions

**Definition of Done:**
- [ ] All 18–20 slides complete, styled consistently
- [ ] Each team member has reviewed and approved their section
- [ ] Demo walkthrough section has screenshots as backup (in case live demo fails)
- [ ] Rehearsal script written with timing per section
- [ ] Dry run completed: full 30-min presentation timed

---

# Timeline

```
Phase 0: Apr 19–23 (5 days) — Local Preparation, No Cloud Cost
═══════════════════════════════════════════════════════════════

Day 1–2 (Apr 19–20):
  Duy:   0.8 Terraform config ────→ CI/CD workflows
  Kien:  0.2 MLCore.py (pre-race + in-race models) ──────→ brief Long
  Hieu:  0.1 Schema design (PostgreSQL + InfluxDB) ──────→
  Thanh: 0.4 Simulation Service ──→ 0.4b Pub/Sub schemas
  Long:  Slide deck structure + architecture diagrams ───→

Day 3–4 (Apr 21–22):
  Duy:   0.6 Docker-compose (deps ready) → 0.7 Dockerize Streamlit
  Kien:  0.2b Model Serving API contract + app.py → 0.3 DataCrawler GCS
  Hieu:  (buffer — review, help others, slides)
  Thanh: 0.5 Pre-cache replays → (buffer — slides, help)
  Long:  Slide content: tech justification drafts

Day 5 (Apr 23):
  ALL:   Buffer / slides / local integration testing


Phase 1: Apr 24 (1 day) — GCP Provisioning, Duy Leads
══════════════════════════════════════════════════════

  Duy:   1.1 terraform apply → 1.2 verify Pub/Sub → 1.4 VM setup → 1.5 verify
  Hieu:  1.3 Cloud SQL: run init.sql, verify tables
  Kien:  (slides: ML section)
  Thanh: (slides: streaming section)
  Long:  (slides: continued)


Phase 2: Apr 25–29 (5 days) — Pipeline Integration, Max Parallelism
════════════════════════════════════════════════════════════════════

Day 1–2 (Apr 25–26):
  Duy:   2.2 Deploy Model API on VM → 2.5 SimService on VM
  Kien:  (slides — blocked on 2.1 + 2.2)
  Hieu:  2.1 Spark Batch on Dataproc (10h) ──────────────────→
  Thanh: 2.3 Streaming fast path on Dataproc ─────────────────→
  Long:  2.6 Streamlit live race panels ──────────────────────→

Day 3–4 (Apr 27–28): ← 2.1 + 2.2 done → Kien unblocked
  Duy:   (buffer — debug, CI/CD polish, help others)
  Kien:  2.4 Streaming slow path ─────────────────────────────→
  Hieu:  3.0 Data quality → 3.1 Batch verify
  Thanh: 3.3 Verify fast path → (help Hieu or Long)
  Long:  2.7 Streamlit PostgreSQL query layer → 2.8 Health panel

Day 5 (Apr 29):
  Duy:   2.9 Deploy Streamlit to Cloud Run
  Kien:  3.4 Verify slow path → 3.7 Kill slow-path test
  Hieu:  (slides / help)
  Thanh: (slides / help)
  Long:  (slides: demo walkthrough)


Phase 3: Apr 30 – May 1 (2 days) — Testing & Validation
════════════════════════════════════════════════════════

  Duy:   3.2 Verify Pub/Sub → 3.8 Verify health panel
  Kien:  3.4 Verify slow path → 3.7 Kill slow-path demo test
  Hieu:  3.0 Data quality (if not done) → 3.1 Batch verify
  Thanh: 3.3 Verify fast path → help dress rehearsal
  Long:  3.5 Verify historical → 3.6 Verify live → finalize slides

  ALL:   3.9 Full dress rehearsal + 30-min slide run-through


Phase 4: Demo Day
═════════════════

  Duy:   Start VM + Cloud SQL (4.1), submit Dataproc jobs (4.2), terraform destroy (4.5)
  Long:  Lead presentation, manage slide transitions, run live demo
  ALL:   Each presents their section (~5 min each)
```

---

# Hours Summary

| Person | Dev | Slides | Total | Critical Dependency |
|--------|-----|--------|-------|---------------------|
| **Duy** | 16.5 | 0.5 | **17** | Phase 1 critical path — everyone waits on terraform |
| **Kien** | 19.75 | 1.5 | **21** | Blocked by 2.1+2.2 in Phase 2 (fills gap with slides) |
| **Hieu** | 17 | 1 | **18** | 2.1 Spark Batch (10h) blocks Kien + Long |
| **Thanh** | 13.5 | 1 | **14.5** | Lightest — flex capacity to help others |
| **Long** | 13.5 | 5 | **18.5** | Slide lead compensates lighter dev load |
| **Total** | | | **~89** | |

**Bottleneck:** Hieu's 2.1 (10h) + Duy's 2.2 → unblocks Kien's 2.4 and Long's 2.7. Thanh is flex to help wherever needed.
