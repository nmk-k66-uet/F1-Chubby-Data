# F1-Chubby-Data: Revised System Architecture & Demo Plan

## Overview

A big-data pipeline for Formula 1 race analytics and real-time prediction, built as a Final Term Project demo. The system ingests historical and live (simulated) F1 data through a multi-layer architecture: ingestion, storage, batch/stream processing, and visualization — all running on Azure managed services.

The serving layer uses **two databases matched to workload type**: PostgreSQL for relational historical analytics, InfluxDB for time-series live streaming data. During a live/simulated race, visualization of race data is **never blocked** by prediction — the two streaming paths are fully decoupled.

---

## Architecture

### High-Level Data Flow

```mermaid
flowchart LR
    subgraph Source
        FIA[FIA API / FastF1]
        SIM[Real-Time Simulation]
    end

    subgraph Ingestion
        DC[DataCrawler<br/>Extended]
    end

    subgraph Storage
        BLOB[Azure Blob Storage]
        KAFKA[Kafka<br/>Azure Event Hubs]
    end

    subgraph Processing
        SPARKB[Spark Batch]
        FE[Feature Eng<br/>+ Model Training]
        FAST[Spark Streaming<br/>Fast Path]
        SLOW[Spark Streaming<br/>Slow Path]
    end

    subgraph Serving
        PG[(PostgreSQL<br/>Historical)]
        INFLUX[(InfluxDB<br/>Live)]
    end

    subgraph Visualization
        UI[Streamlit App]
    end

    FIA --> DC --> BLOB
    SIM --> KAFKA

    BLOB --> SPARKB --> FE
    FE --> PG
    FE -->|model artifact| BLOB

    KAFKA --> FAST --> INFLUX
    KAFKA --> SLOW -->|predictions| INFLUX

    PG --> UI
    INFLUX --> UI
```

### Batch Processing Detail

```mermaid
flowchart TD
    BLOB[Azure Blob Storage<br/>/raw/year/round/session/] --> LOAD[Data Load + Transform]
    LOAD --> FEAT[Feature Engineering<br/>GridPos, QualDelta, PaceDelta,<br/>DriverForm, TeamTier]
    FEAT --> PRE_MODEL[Pre-Race Model Training<br/>RandomForest Classifier<br/>Target: Podium Probability]
    FEAT --> IN_MODEL[In-Race Model Training<br/>RandomForest Regressor<br/>Target: Finishing Position]
    PRE_MODEL -->|pre_race_model.pkl| BLOB_OUT[Blob /ml-models/]
    IN_MODEL -->|in_race_model.pkl| BLOB_OUT
    FEAT --> PG_WRITE[Write to PostgreSQL via JDBC]
    PG_WRITE --> T1[race_calendar]
    PG_WRITE --> T2[session_results]
    PG_WRITE --> T3[driver_standings]
    PG_WRITE --> T4[constructor_standings]
    PG_WRITE --> T5[lap_times]
    PG_WRITE --> T6[telemetry_summary]
    PG_WRITE --> T7[ml_features]
    PG_WRITE --> T8[prediction_accuracy]
    PG_WRITE --> DQ[data_quality<br/>Row count validation]
```

### Streaming Processing Detail

```mermaid
flowchart TD
    subgraph KT ["Kafka Topics"]
        T1[f1-telemetry<br/>~10 Hz per car]
        T2[f1-timing<br/>per lap per car]
        T3[f1-race-control<br/>event-driven]
    end

    subgraph FP ["Fast Path | consumer group: viz-fast"]
        F_PARSE[Parse JSON +<br/>Validate Schema]
        F_ENRICH[Enrich with<br/>Driver/Team Metadata]
        F_WRITE[Write to InfluxDB<br/>Sub-second latency]
    end

    subgraph SP ["Slow Path | consumer group: pred-slow"]
        S_WINDOW[Windowed Feature<br/>Computation<br/>5-10 sec windows]
        S_MODEL[Load In-Race Model<br/>from Blob]
        S_INFER[Run Inference]
        S_WRITE[Write to InfluxDB<br/>predictions bucket]
    end

    T1 & T2 & T3 --> F_PARSE --> F_ENRICH --> F_WRITE
    T1 & T2 & T3 --> S_WINDOW --> S_MODEL --> S_INFER --> S_WRITE

    F_WRITE --> LP[live_positions]
    F_WRITE --> LTI[live_timing]
    F_WRITE --> LRC[live_race_control]
    S_WRITE --> PRED[predictions]
```

### Dual-Database Serving Strategy

```mermaid
flowchart LR
    subgraph PG ["PostgreSQL | Historical"]
        RC[race_calendar]
        SR[session_results]
        DS[driver_standings]
        CS[constructor_standings]
        LT[lap_times]
        TS[telemetry_summary]
        MF[ml_features]
        PA[prediction_accuracy]
        DQ[data_quality]
    end

    subgraph IDB ["InfluxDB | Live"]
        LP[live_positions]
        LTM[live_timing]
        LRC[live_race_control]
        PRED[predictions]
    end

    subgraph FF1 ["FastF1 Cache | High-Res Telemetry"]
        REPLAY[Race Replay<br/>100ms interpolated X/Y]
        DOM[Track Dominance<br/>per-meter Distance index]
        GEAR[Gear Shift Maps]
    end

    subgraph ST ["Streamlit"]
        HIST[Historical Views]
        LIVE[Live Race Views]
        HIRES[Replay + Dominance]
        HEALTH[Pipeline Health]
    end

    RC & SR & DS & CS & LT & TS & MF & PA --> HIST
    LP & LTM & LRC & PRED --> LIVE
    REPLAY & DOM & GEAR --> HIRES
    DQ --> HEALTH
```

---

## Component Specification

### 1. Source Layer

#### FIA API (via FastF1)

- **Role:** Primary data source for historical F1 data.
- **Coverage:** 2019–2025 for telemetry-dependent features (telemetry quality degrades before 2019), 2018–2025 for results/standings.
- **Data includes:** Race calendars, session results, qualifying times, lap times, pit stops, driver/constructor standings, telemetry, race control messages.
- **Interaction:** Feeds into the DataCrawler (`FIA --> DC`).

#### Real-Time Simulation Service

- **Role:** Replays a pre-cached historical race into Kafka, simulating a live race feed for demo day.
- **Why needed:** Cannot guarantee a real race on demo day.
- **Behavior:**
  - Reads pre-extracted telemetry for a historical race (stored as parquet/JSON in Blob under `replay-cache/`).
  - Publishes to three Kafka topics at configurable speed (e.g., 5× → ~18 min race).
  - Produces directly to Kafka (`SIM --> KAFKA`), bypassing DataCrawler. This is intentional — during a real race the DataCrawler handles API data; during demo, the Simulation Service substitutes it.
- **Configuration:**
  - `REPLAY_SPEED` — Speed multiplier (default `5.0`).
  - `REPLAY_RACE` — Which cached race to replay (e.g., `2024_bahrain_R`).
- **Pre-caching:** A one-time script extracts a full race session from FastF1, interpolates all cars to a unified 10 Hz timeline, and uploads to Blob under `replay-cache/`.

### 2. Ingestion Layer

#### DataCrawler (Extended)

- **Role:** Extends the existing `DataCrawler.py` to serve as the ingestion layer. Extracts data from the FIA API via FastF1, normalizes it, saves locally, and uploads raw data to Azure Blob Storage.
- **Outputs:**
  - **To Blob** (`DC --> BLOB`): Raw session data, partitioned as `/raw/{year}/{round}/{session}/`. Used by the batch processing path.
  - **To local CSV** (`f1_cache/historical_data_v2.csv`): ML training features (existing behavior, preserved).
- **Implementation:** Already exists as `DataCrawler.py`. Extended with `azure-storage-blob` SDK calls for Blob upload. Handles API rate limits (15s delay), retries, and resumable crawling (existing checkpoint logic).
- **Why not a separate Ingestion Service:** The DataCrawler already does extraction + normalization + resumable crawling. Adding Blob upload is ~30 lines of code. Building a separate service adds ~4 hours of work with no architectural benefit for a PoC.

### 3. Storage Layer

#### Azure Blob Storage

- **Role:** Durable store for raw historical data, model artifacts, and replay cache.
- **Containers:**
  - `raw/` — Raw session data from DataCrawler, partitioned by `{year}/{round}/{session}/`.
  - `ml-models/` — Trained model artifacts (`pre_race_model.pkl`, `in_race_model.pkl`).
  - `replay-cache/` — Pre-extracted race telemetry for the Simulation Service.
- **Azure SKU:** GPv2, LRS, Hot tier.

#### Kafka (Azure Event Hubs)

- **Role:** Streaming message bus for live/simulated race data.
- **Topics (Event Hubs):**
  - `f1-telemetry` — High-frequency car telemetry.
  - `f1-timing` — Per-lap timing data.
  - `f1-race-control` — Race director messages and flags.
- **Message Schemas:** Defined as JSON Schema documents in `/schemas/` directory. All producers and consumers reference these schemas (see [Kafka Message Schemas](#kafka-message-schemas)).
- **Azure SKU:** Event Hubs Standard, 1 Throughput Unit, Kafka protocol enabled.
- **Retention:** 1 day (sufficient for demo).

### 4. Serving Layer (Dual-Database)

The serving layer uses two databases, each matched to its workload type. This is a deliberate architectural decision: relational analytics need JOINs, GROUP BY, ORDER BY, and window functions; live streaming data needs fast time-indexed appends and time-range queries.

```mermaid
flowchart TD
    Q1["GROUP BY (Driver, Stint, Compound)"] --> PG[(PostgreSQL)]
    Q2["ORDER BY Position"] --> PG
    Q3["JOIN results ⋈ standings"] --> PG
    Q4["Window: LAG/LEAD for gaps"] --> PG

    Q5["Append car position @ timestamp"] --> INFLUX[(InfluxDB)]
    Q6["Range query: last 30 seconds"] --> INFLUX
    Q7["Downsample: 10Hz → 1Hz"] --> INFLUX
```

#### PostgreSQL — Historical Analytics

- **Role:** Serving database for all historical/batch-processed data.
- **Deployment:** Azure Database for PostgreSQL Flexible Server.
- **Azure SKU:** Burstable B1ms (1 vCPU, 2 GB RAM). **Stopped when idle** to save cost.
- **Why PostgreSQL over InfluxDB for historical data:**
  - Dashboard queries involve complex SQL: `GROUP BY`, `ORDER BY`, `JOIN`, window functions.
  - FastF1 data is fundamentally relational: results are tabular, laps indexed by LapNumber (not timestamp), telemetry indexed by Distance (meters).
  - InfluxDB's Flux query language cannot express multi-key aggregations, pivots, or JOINs.

- **Tables:**

  | Table | Source | Contents | Dashboard View |
  |-------|--------|----------|----------------|
  | `race_calendar` | Spark Batch | Season schedules, event dates, circuits, country codes | Calendar page |
  | `session_results` | Spark Batch | Finishing order, grid, points, status, times per driver per session | Results tab |
  | `driver_standings` | Spark Batch | Championship points after each round | Standings page |
  | `constructor_standings` | Spark Batch | Constructor championship points after each round | Standings page |
  | `lap_times` | Spark Batch | Lap-by-lap times, compounds, stints, tyre life | Lap times chart, strategy analysis |
  | `telemetry_summary` | Spark Batch | Aggregated sector speeds, top speeds per session per driver | Telemetry comparison |
  | `ml_features` | Spark Batch | Engineered features for ML (grid position, qualifying delta, pace delta, driver form, team tier) | Feature store, pre-race predictions |
  | `prediction_accuracy` | Spark Batch | Historical prediction vs. actual results | Model accuracy dashboard |
  | `data_quality` | Spark Batch | Row count validation, schema checks per season/table | Pipeline health panel |

#### InfluxDB — Live Streaming Data

- **Role:** Serving database for live/simulated race data and real-time predictions.
- **Deployment:** InfluxDB 2.x OSS in Docker on the Azure VM (shared with Simulation Service).
- **Why InfluxDB for live data:** Append-heavy writes from streaming, time-indexed queries, short retention, no complex joins needed.

- **Measurements:**

  | Bucket | Source | Contents | Retention |
  |--------|--------|----------|-----------|
  | `live_positions` | Spark Streaming (fast path) | Real-time car X/Y, speed — high frequency | 7 days |
  | `live_timing` | Spark Streaming (fast path) | Real-time lap times, gaps, positions — per lap | 7 days |
  | `live_race_control` | Spark Streaming (fast path) | Real-time flags, safety car, incidents | 7 days |
  | `predictions` | Spark Streaming (slow path) | Podium probabilities, position predictions with staleness timestamp | 7 days |

### 5. Processing Layer

#### Spark Batch

- **Role:** Processes all historical data from Blob, engineers ML features, trains models, and populates PostgreSQL.
- **Jobs:**
  1. **Data Load + Transform** — Read raw data from Blob, clean, normalize, resolve schema differences across seasons.
  2. **Feature Engineering** — Compute features: grid position, qualifying delta, FP2/Sprint pace delta, driver form, team tier, tyre strategy metrics.
  3. **Pre-Race Model Training** — scikit-learn RandomForest classifier on engineered features. Save to Blob (`ml-models/pre_race_model.pkl`).
  4. **In-Race Model Training** — Trained on historical in-race snapshots (lap-by-lap state → final result). Save to Blob (`ml-models/in_race_model.pkl`).
  5. **Historical Data Load** — Write all processed data to PostgreSQL via JDBC connector.
  6. **Data Quality Validation** — Row count checks per season per table. Write results to `data_quality` table.
- **Platform:** Azure Databricks Standard, single-node Jobs Compute cluster (D4as v5), auto-terminate after 10 min idle.

#### Spark Streaming — Fast Path

- **Role:** Consumes live/simulated race data from Kafka and writes visualization data to InfluxDB with sub-second latency. **No model dependency.**
- **Input:** `f1-telemetry`, `f1-timing`, `f1-race-control` topics (consumer group: `viz-fast`).
- **Processing:** Parse JSON (validate against schemas), enrich with driver/team metadata (broadcast lookup), convert timestamps.
- **Output:** InfluxDB `live_positions`, `live_timing`, `live_race_control`.
- **Latency:** Sub-second micro-batches.
- **Failure isolation:** If this job fails, only live visualization is affected. Predictions continue independently.

#### Spark Streaming — Slow Path

- **Role:** Consumes live data, computes windowed features, runs model inference, writes predictions to InfluxDB.
- **Input:** Same Kafka topics (separate consumer group: `pred-slow`).
- **Processing:** Windowed feature computation + load in-race model from Blob + inference.
- **Output:** InfluxDB `predictions` with prediction freshness timestamp.
- **Latency:** 5–10 second windows.
- **Failure isolation:** If prediction lags or crashes, live visualization is completely unaffected.

##### Why Two Separate Streaming Jobs

Full **backpressure isolation**. In a single Structured Streaming job with two sinks, if the prediction model is slow, Spark's micro-batch scheduling delays the entire batch — including the visualization sink. Separate jobs have independent scheduling. For a demo where reliability matters, this is the right tradeoff at marginal additional cost.

```mermaid
flowchart TD
    subgraph "Single Job (rejected)"
        K1[Kafka] --> MB1[Micro-Batch]
        MB1 --> VIZ1[Viz Sink]
        MB1 --> PRED1[Prediction Sink<br/>⚠️ slow model blocks viz]
    end

    subgraph "Two Jobs (chosen) ✅"
        K2[Kafka] --> JOB1[Job 1: Fast Path<br/>Independent scheduling]
        K2 --> JOB2[Job 2: Slow Path<br/>Independent scheduling]
        JOB1 --> VIZ2[Viz Sink<br/>sub-second]
        JOB2 --> PRED2[Prediction Sink<br/>5–10 sec, no impact on viz]
    end
```

### 6. ML Component

Two distinct models serve different prediction scenarios:

```mermaid
flowchart LR
    subgraph Pre-Race Model
        F1[GridPosition]
        F2[QualifyingDelta]
        F3[FP2_PaceDelta]
        F4[DriverForm]
        F5[TeamTier]
        F1 & F2 & F3 & F4 & F5 --> RF1[RandomForest<br/>Classifier]
        RF1 --> P1[Podium Probability<br/>Before lights out]
    end

    subgraph In-Race Model
        L1[CurrentPosition]
        L2[GapToLeader]
        L3[TyreCompound]
        L4[TyreAge]
        L5[PitStopsMade]
        L6[SafetyCarActive]
        L7[LapsRemaining]
        L1 & L2 & L3 & L4 & L5 & L6 & L7 --> RF2[RandomForest<br/>Regressor]
        RF2 --> P2[Predicted Finishing Pos<br/>Updated every 5–10 sec]
    end
```

#### Pre-Race Model
- **Features:** GridPosition, TeamTier, QualifyingDelta, FP2_PaceDelta, DriverForm (from `DataCrawler.py` feature engineering).
- **Target:** Podium probability (binary: top 3 finish).
- **Training:** Spark Batch job, scikit-learn RandomForest.
- **Inference:** Run once per race as batch, results stored in PostgreSQL `prediction_accuracy`.
- **Purpose:** "Before the race starts, here's who we think will podium."

#### In-Race Model
- **Features:** CurrentPosition, GapToLeader, TyreCompound, TyreAge, PitStopsMade, SafetyCarActive, LapsRemaining.
- **Target:** Predicted finishing position.
- **Training:** Spark Batch job, trained on historical in-race snapshots (lap-by-lap state → final result).
- **Inference:** Spark Streaming slow path, updated every 5–10 seconds.
- **Purpose:** "Right now, lap 35, here's the predicted finishing order."

### 7. Visualization Layer

#### Streamlit App

- **Role:** User-facing dashboard. Reads from PostgreSQL (historical), InfluxDB (live), and FastF1 cache (high-res telemetry).

```mermaid
flowchart TD
    subgraph Streamlit Dashboard
        CAL[Calendar Page]
        RES[Results Tab]
        STAND[Standings Page]
        LAPS[Lap Times Chart]
        STRAT[Strategy Analysis]
        TEL[Telemetry Comparison]
        REPLAY[Race Replay Engine]
        DOM[Track Dominance]
        LIVE_T[Live Race Tracker]
        LIVE_TM[Live Timing Board]
        LIVE_RC[Race Control Feed]
        LIVE_P[AI Predictions Panel<br/>+ Staleness Indicator]
        HEALTH[Pipeline Health Panel]
    end

    PG[(PostgreSQL)] --> CAL & RES & STAND & LAPS & STRAT & TEL
    INFLUX[(InfluxDB)] --> LIVE_T & LIVE_TM & LIVE_RC & LIVE_P
    FF1[FastF1 Cache] --> REPLAY & DOM
    MONITOR[Azure Monitor<br/>+ DB Metadata] --> HEALTH
```

- **Data sources by view:**

  | View | Database | Query Method |
  |------|----------|-------------|
  | Calendar, event list | PostgreSQL | `psycopg2` / SQLAlchemy |
  | Session results, standings | PostgreSQL | SQL queries |
  | Lap time charts, strategy analysis | PostgreSQL | SQL with GROUP BY |
  | Telemetry comparison | PostgreSQL + FastF1 cache | SQL + fallback |
  | Race replay engine | FastF1 cache (requires 100ms interpolated X/Y) | Existing logic |
  | Track dominance, gear maps | FastF1 cache (per-meter Distance index) | Existing logic |
  | **Live race tracker** | InfluxDB `live_positions` | `influxdb-client` |
  | **Live timing board** | InfluxDB `live_timing` | `influxdb-client` |
  | **Race control feed** | InfluxDB `live_race_control` | `influxdb-client` |
  | **AI Predictions panel** | InfluxDB `predictions` | `influxdb-client` |
  | **Pipeline health** | Azure Monitor + DB metadata | REST API + queries |

- **Prediction Staleness Indicator:** Live predictions panel displays the timestamp of the last prediction update. If >15 seconds stale, show warning badge. Makes the fast/slow path latency tradeoff visible.

- **Pipeline Health Panel:**
  - Kafka consumer lag (via Event Hubs metrics / Azure Monitor)
  - Last write timestamp per InfluxDB measurement and PostgreSQL table
  - Spark job status (Databricks REST API)
  - Data quality summary (from PostgreSQL `data_quality` table)

- **High-Resolution Telemetry:** Race replay, track dominance, and gear maps require 100ms-interpolated X/Y coordinates and per-meter Distance indexing. This data is too granular for either database to serve efficiently. **Keep the existing FastF1 cache + Pandas in-memory approach.** The batch pipeline loads summary-level telemetry to PostgreSQL; full-resolution telemetry is served from cache.

- **Deployment:** Azure App Service, B1 Linux.

---

## Azure Infrastructure

### Resource Group Contents

| Resource | Azure Service | SKU | Purpose |
|----------|---------------|-----|---------|
| Event Hubs Namespace | Event Hubs | Standard, 1 TU, Kafka-enabled | Kafka message bus (3 topics) |
| Storage Account | Blob Storage | GPv2, LRS, Hot | Raw data, models, replay cache |
| PostgreSQL Server | DB for PostgreSQL Flexible | Burstable B1ms (stop when idle) | Historical analytics serving DB |
| Virtual Machine | Compute | B2als v2 (2 vCPU, 4 GB) | Hosts InfluxDB + Simulation Service |
| Databricks Workspace | Databricks | Standard | Spark Batch + 2× Spark Streaming |
| App Service | App Service | B1 Linux | Streamlit dashboard |

### Infrastructure Topology

```mermaid
flowchart TD
    subgraph Azure Resource Group
        subgraph Networking
            VNET[Virtual Network]
        end

        subgraph Compute
            VM[VM: B2als v2<br/>Docker: InfluxDB + SimService]
            DB_BATCH[Databricks Cluster 1<br/>Batch Job]
            DB_FAST[Databricks Cluster 2<br/>Streaming Fast Path]
            DB_SLOW[Databricks Cluster 3<br/>Streaming Slow Path]
            APP[App Service: B1<br/>Streamlit]
        end

        subgraph Data
            EH[Event Hubs Namespace<br/>1 TU, Kafka]
            BLOB[Storage Account<br/>GPv2, LRS, Hot]
            PG[PostgreSQL Flexible<br/>B1ms]
        end
    end

    BICEP[infra/main.bicep] -->|az deployment<br/>group create| Azure Resource Group
```

### Provisioning: Infrastructure as Code

All resources provisioned via a **Bicep template** (`infra/main.bicep`):
- Makes teardown/re-creation trivial (`az group delete`)
- Enables reproducible setup across team members
- Demonstrates DevOps maturity (grading point)
- Includes parameterized SKUs, connection strings output

### Estimated Cost (8 days: 7 dev + 1 demo)

| Component | Est. Cost |
|-----------|-----------|
| Event Hubs (1 TU, 8 days) | ~$6 |
| Blob Storage (~3–5 GB) | ~$0.15 |
| PostgreSQL Flexible B1ms (~4 days active, stopped otherwise) | ~$1.60 |
| VM + disk (B2als v2, 8 days) | ~$8 |
| Databricks Standard Jobs Compute (~10 hrs total) | ~$4 |
| App Service (B1, 8 days) | ~$3.50 |
| **Total** | **~$23** |

> Budget recommendation: ~$35 with 50% buffer. Delete the Resource Group immediately after demo.

### Cost-Saving Practices

- **Stop PostgreSQL** when not actively developing (`az postgres flexible-server stop`).
- **Deallocate the VM** when not actively developing.
- **Auto-terminate** Databricks clusters after 10 min idle.
- **1-day retention** on Event Hubs.
- **Delete the entire Resource Group** after the demo.

---

## Kafka Message Schemas

Defined in `/schemas/` directory. All producers (Simulation Service) and consumers (Spark Streaming) reference these.

### `f1-telemetry` (per car, ~10 Hz)

```json
{
  "timestamp_ms": 1712345678900,
  "driver_id": "VER",
  "x": 1234.5,
  "y": 5678.9,
  "speed_kph": 312.4,
  "throttle_pct": 100.0,
  "brake_pct": 0.0,
  "gear": 8,
  "drs": 1,
  "lap_number": 15,
  "session_time_sec": 1845.3
}
```

### `f1-timing` (per car per lap)

```json
{
  "timestamp_ms": 1712345700000,
  "driver_id": "VER",
  "lap_number": 15,
  "position": 1,
  "lap_time_ms": 88234,
  "gap_to_leader_ms": 0,
  "interval_ms": 0,
  "tyre_compound": "MEDIUM",
  "tyre_age_laps": 8,
  "stint_number": 2,
  "pit_in_lap": false,
  "pit_out_lap": false
}
```

### `f1-race-control` (event-driven)

```json
{
  "timestamp_ms": 1712345750000,
  "flag": "YELLOW",
  "scope": "SECTOR_2",
  "message": "Yellow flag in sector 2",
  "driver_id": "HAM",
  "lap_number": 16
}
```

---

## Task Breakdown

### Phase Overview

```mermaid
gantt
    title Project Phases
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Phase 0
    Local Preparation (no Azure cost)    :p0, 2026-04-12, 5d

    section Phase 1
    Azure Provisioning                   :p1, after p0, 1d

    section Phase 2
    Pipeline Integration                 :p2, after p1, 5d

    section Phase 3
    Testing & Validation                 :p3, after p2, 2d

    section Phase 4
    Demo Day                             :milestone, after p3, 0d
```

### Phase 0: Local Preparation (no Azure cost)

| # | Task | Depends On | Est. Effort |
|---|------|------------|-------------|
| 0.1 | Design PostgreSQL schema (tables, columns, types, indexes, FK constraints) + InfluxDB measurements (4 live: tags, fields, timestamp semantics) | — | 4 hrs |
| 0.2 | Implement `MLCore.py`: pre-race model (podium classifier on DataCrawler features) + in-race model (position predictor on live features). Training + serialized prediction interface. | — | 5 hrs |
| 0.3 | Extend `DataCrawler.py`: add `azure-storage-blob` upload after extraction. Validate 2018–2025 coverage (telemetry from 2019+, results from 2018+). | — | 2 hrs |
| 0.4 | Build Simulation Service: read cached race from Blob → replay to Kafka at configurable speed | — | 4 hrs |
| 0.4b | Define Kafka message JSON schemas for all 3 topics (in `/schemas/` directory) | — | 1.5 hrs |
| 0.5 | Pre-cache 2–3 race replays as parquet (interpolated to 10 Hz unified timeline) | 0.4 | 1 hr |
| 0.6 | Dockerize InfluxDB + Simulation Service (`docker-compose.yml` for local testing) | 0.1, 0.4 | 2 hrs |
| 0.7 | Dockerize Streamlit app | — | 1 hr |
| 0.8 | Write IaC template (`infra/main.bicep`) — all Azure resources parameterized | — | 3 hrs |

**Phase 0 subtotal: ~23.5 hrs**

### Phase 1: Azure Infrastructure Provisioning

| # | Task | Depends On | Est. Effort |
|---|------|------------|-------------|
| 1.1 | Deploy IaC (`az deployment group create`), upload raw data + replay cache to Blob | 0.3, 0.5, 0.8 | 30 min |
| 1.2 | Verify Event Hubs namespace + 3 Event Hubs created by IaC | 0.8 | 10 min |
| 1.3 | Verify PostgreSQL Flexible Server, create tables + indexes from schema DDL | 0.1, 0.8 | 20 min |
| 1.4 | VM: install Docker, deploy InfluxDB container, initialize buckets from schema | 0.1, 0.8 | 30 min |
| 1.5 | Verify Databricks Workspace + App Service created by IaC | 0.8 | 10 min |

**Phase 1 subtotal: ~1.5 hrs**

### Phase 2: Pipeline Integration

| # | Task | Depends On | Est. Effort | Parallel Stream |
|---|------|------------|-------------|-----------------|
| 2.1 | Spark Batch notebook: Blob → data load + transform + feature engineering → PostgreSQL (JDBC) + model artifacts → Blob | 1.1, 1.3, 1.5, 0.2 | 10 hrs | A |
| 2.2 | Spark Streaming fast path: Event Hubs → parse/validate JSON → enrich metadata → InfluxDB live measurements | 1.2, 1.4, 1.5, 0.4b | 6 hrs | B |
| 2.3 | Spark Streaming slow path: Event Hubs → windowed features → load in-race model → inference → InfluxDB predictions | 1.2, 1.4, 1.5, 2.1 | 7 hrs | B (after 2.1) |
| 2.4 | Configure Simulation Service on VM to produce to Event Hubs | 1.2, 1.4, 0.4 | 2 hrs | C |
| 2.5 | Streamlit: add live race panels (tracker, timing board, race control feed, AI predictions + staleness indicator) — InfluxDB | 0.1 | 5 hrs | C |
| 2.6 | Streamlit: add PostgreSQL query layer for historical views (SQL queries alongside existing FastF1 cache logic) | 1.3, 2.1 | 4 hrs | A (after 2.1) |
| 2.7 | Streamlit: add pipeline health panel (Kafka lag, DB freshness, Spark job status, data quality) | 2.1, 2.2 | 3 hrs | C (after 2.1, 2.2) |
| 2.8 | Deploy Streamlit app to App Service | 2.5, 2.6, 2.7 | 1 hr | — |

**Phase 2 subtotal: ~38 hrs**

### Phase 3: End-to-End Testing & Validation

| # | Task | Depends On | Est. Effort |
|---|------|------------|-------------|
| 3.0 | Data quality validation: row-count checks per season per PostgreSQL table, schema consistency, log to `data_quality` | 2.1 | 2 hrs |
| 3.1 | Run Spark Batch end-to-end, verify all historical data in PostgreSQL, model artifacts in Blob | 2.1 | 1 hr |
| 3.2 | Start Simulation → verify events arrive in Event Hubs (check portal metrics) | 2.4 | 30 min |
| 3.3 | Start fast-path streaming → verify live data in InfluxDB within 1 sec | 2.2, 3.2 | 1 hr |
| 3.4 | Start slow-path streaming → verify predictions in InfluxDB (independent of fast path) | 2.3, 3.2 | 1 hr |
| 3.5 | Open Streamlit → verify historical views from PostgreSQL | 2.6, 3.1 | 30 min |
| 3.6 | Open Streamlit → verify live views update from fast path, predictions update independently from slow path | 3.3, 3.4 | 1 hr |
| 3.7 | **Kill slow-path job → confirm live visualization continues uninterrupted** *(key demo moment)* | 3.6 | 15 min |
| 3.8 | Verify pipeline health panel shows correct status for all components | 2.7, 3.3, 3.4 | 30 min |
| 3.9 | Full dress rehearsal: complete demo flow at 5× speed | 3.0–3.8 | 2 hrs |

**Phase 3 subtotal: ~10 hrs**

### Phase 4: Demo Day

| # | Task | Depends On | Est. Effort |
|---|------|------------|-------------|
| 4.1 | Start VM (InfluxDB + Simulation Service) + start PostgreSQL | 3.9 | 5 min |
| 4.2 | Start both Databricks Streaming clusters | 3.9 | 3 min |
| 4.3 | Verify Streamlit app is live, pipeline health panel green | 3.9 | 2 min |
| 4.4 | Run demo: architecture walkthrough (~5 min) + live simulation (~15–18 min) | 4.1–4.3 | 25 min |
| 4.5 | **Tear down: Delete Resource Group** | 4.4 | 5 min |

---

## Total Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 0: Local Preparation | ~23.5 hrs |
| Phase 1: Azure Provisioning | ~1.5 hrs |
| Phase 2: Pipeline Integration | ~38 hrs |
| Phase 3: Testing & Validation | ~10 hrs |
| Phase 4: Demo Day | ~30 min |
| **Total** | **~73.5 person-hours** |

---

## Parallel Work Streams (2–3 team members)

```mermaid
flowchart TD
    subgraph "Stream A — Batch + DB"
        A1[0.1 Schema Design] --> A2[0.8 IaC Template]
        A2 --> A3[2.1 Spark Batch]
        A3 --> A4[2.6 Streamlit PostgreSQL]
        A3 --> A5[3.0 Data Quality]
    end

    subgraph "Stream B — Streaming + ML"
        B1[0.2 MLCore.py] --> B2[0.3 Extend DataCrawler]
        B2 --> B3[2.2 Streaming Fast Path]
        B3 --> B4[2.3 Streaming Slow Path]
        B4 --> B5[3.3–3.4 Streaming Tests]
    end

    subgraph "Stream C — Frontend + Infra"
        C1[0.4 Simulation Service] --> C2[0.4b Kafka Schemas]
        C2 --> C3[2.4 Simulation on VM]
        C3 --> C4[2.5 Streamlit Live Panels]
        C4 --> C5[2.7 Health Panel]
    end

    A3 -->|trained model| B4
    A4 & B5 & C5 --> DEPLOY[2.8 Deploy to App Service]
    DEPLOY --> TEST[3.5–3.9 E2E Testing]
```

| Stream A (Batch + DB) | Stream B (Streaming + ML) | Stream C (Frontend + Infra) |
|------------------------|---------------------------|------------------------------|
| 0.1 Schema design | 0.2 MLCore.py | 0.4 Simulation Service |
| 0.8 IaC template | 0.3 Extend DataCrawler | 0.4b Kafka schemas |
| 2.1 Spark Batch | 2.2 Streaming fast path | 2.4 Simulation on VM |
| 2.6 Streamlit PostgreSQL | 2.3 Streaming slow path | 2.5 Streamlit live panels |
| 3.0 Data quality | 3.3–3.4 Streaming tests | 2.7 Health panel |

---

## Key Design Decisions

### 1. Dual-Database Serving Layer (PostgreSQL + InfluxDB)

Workload-driven database selection:
- **PostgreSQL** for historical data: the dashboard requires `GROUP BY (Driver, Stint, Compound)`, `ORDER BY Position`, JOINs, and window functions — all native SQL. FastF1's data model is fundamentally relational.
- **InfluxDB** for live streaming: append-heavy, time-indexed, short retention, no joins. Time-series DB is the right tool.
- Demonstrates understanding of database selection tradeoffs.

### 2. Decoupled Fast/Slow Streaming Paths

Two independent Spark Streaming jobs with **backpressure isolation**: if the prediction model is slow, Structured Streaming's micro-batch scheduling would delay the entire batch in a single-job design. Separate jobs have independent scheduling. The "kill slow path, fast path continues" test (Task 3.7) is a key demo moment.

### 3. Pragmatic Telemetry Strategy

Summary telemetry (sector speeds, top speeds) is batch-processed into PostgreSQL. Full-resolution telemetry (100ms X/Y interpolation for replay, per-meter Distance indexing for dominance maps) stays in FastF1 cache + Pandas in-memory. Neither PostgreSQL nor InfluxDB serves this data efficiently — and the existing implementation already works.

### 4. Two ML Models (Pre-Race + In-Race)

- **Pre-race**: Historical features → podium probability before lights out.
- **In-race**: Live features → predicted finishing position, updated lap-by-lap.
- Different feature sets, different inference timing, different serving paths. Architecturally clean.

### 5. DataCrawler as Ingestion Layer

Extended `DataCrawler.py` with Blob upload rather than a separate Ingestion Service. Same architectural role, less code to build and maintain. The diagram still shows a distinct ingestion layer.

### 6. Infrastructure as Code

All Azure resources provisioned via Bicep template. Enables reproducible setup, easy teardown, and demonstrates DevOps maturity.

---

## Fallback Plan (Demo Day)

| Failure Scenario | Mitigation |
|------------------|------------|
| PostgreSQL down | Historical views fall back to FastF1 cache (existing code path still works) |
| Event Hubs / Streaming down | Pre-recorded video of live panels + architecture walkthrough |
| Databricks clusters fail to start | Show batch results already in PostgreSQL + explain streaming design |
| Worst case (all Azure down) | Full demo locally: Streamlit + FastF1 cache + architecture diagram |

---

## File Structure

```
F1-Chubby-Data/
├── Dashboard.py                 # Main Streamlit app (extend with PG + InfluxDB)
├── DataCrawler.py               # Extend with Blob upload
├── MLCore.py                    # NEW — Pre-race + in-race models
├── SimulationService.py         # NEW — Kafka replay producer
├── docker-compose.yml           # NEW — InfluxDB + SimService local dev
├── Dockerfile                   # NEW — Streamlit container
├── requirements.txt             # Updated with new dependencies
├── revised_plan.md              # This document
├── infra/
│   └── main.bicep               # NEW — IaC for all Azure resources
├── schemas/
│   ├── f1-telemetry.json        # NEW — Kafka message schema
│   ├── f1-timing.json           # NEW — Kafka message schema
│   └── f1-race-control.json     # NEW — Kafka message schema
├── sql/
│   └── init.sql                 # NEW — PostgreSQL DDL (tables, indexes, FKs)
├── spark/
│   ├── batch_pipeline.py        # NEW — Spark Batch job
│   ├── streaming_fast.py        # NEW — Spark Streaming fast path
│   └── streaming_slow.py        # NEW — Spark Streaming slow path
├── assets/
│   ├── Cars/
│   └── Teams/
└── f1_cache/                    # FastF1 local cache (gitignored)
```
