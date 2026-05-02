# Hệ Thống Phân Tích Dữ Liệu và Dự Đoán Thời Gian Thực Formula 1 trên Google Cloud Platform

**Nhóm:** F1-Chubby-Data
**Khoa:** Công nghệ Thông tin
**Trường:** Đại học Công nghệ - ĐHQGHN

---

## Tóm Tắt

Báo cáo này trình bày việc thiết kế và triển khai một hệ thống phân tích dữ liệu thời gian thực cho đua xe Formula 1, kết hợp xử lý luồng dữ liệu (stream processing), học máy (machine learning), và hạ tầng đám mây. Hệ thống sử dụng Apache Spark trên Google Dataproc cho xử lý phân tán, Google Pub/Sub cho message queue, InfluxDB cho cơ sở dữ liệu chuỗi thời gian, và FastAPI phục vụ mô hình Random Forest dự đoán xác suất thắng cuộc/podium theo từng vòng đua.

Kiến trúc dual-path streaming đạt độ trễ ~500ms cho visualization và ~10s cho ML prediction. Dashboard Streamlit hiển thị telemetry, chiến lược lốp, và cập nhật dự đoán real-time. Toàn bộ infrastructure được quản lý bằng Terraform và triển khai tự động qua GitHub Actions với Workload Identity Federation. Hệ thống đã được triển khai thành công trên GCP và kiểm chứng qua mô phỏng đua thực tế từ dữ liệu mùa giải 2024-2026.

**Từ khóa:** Stream processing, Apache Spark, Machine Learning, Real-time analytics, Formula 1, GCP, InfluxDB, Pub/Sub

---

## 1. Giới Thiệu

### 1.1 Bối Cảnh

Formula 1 là một trong những môn thể thao có lượng dữ liệu lớn nhất, với hàng ngàn điểm dữ liệu telemetry được thu thập mỗi giây từ các cảm biến trên xe đua. Dữ liệu bao gồm vận tốc, RPM động cơ, nhiệt độ lốp, góc lái, áp suất phanh, và vị trí GPS, tạo nên một nguồn thông tin phong phú cho phân tích và dự đoán.

Trong những năm gần đây, các đội đua F1 đã đầu tư mạnh vào data science và machine learning để tối ưu hóa chiến lược đua, từ quyết định thời điểm pit stop đến lựa chọn compound lốp. Tuy nhiên, các công cụ phân tích cho người hâm mộ vẫn còn hạn chế về khả năng xử lý real-time và độ sâu phân tích.

### 1.2 Mục Tiêu Đề Tài

Đề tài này xây dựng một hệ thống end-to-end cho phân tích và dự đoán F1 với các mục tiêu cụ thể:

1. **Thu thập và xử lý dữ liệu quy mô lớn**: Tích hợp FastF1 API, xây dựng cache 3 tầng (local, GCS, API) để tối ưu thời gian tải.

2. **Xử lý phân tán với Spark**: Huấn luyện mô hình ML trên dữ liệu lịch sử 2024-2026 với feature engineering pipeline trên Google Dataproc.

3. **Stream processing real-time**: Xây dựng kiến trúc dual-path với Pub/Sub và InfluxDB, đạt latency < 1 giây cho visualization path.

4. **ML model serving**: Triển khai FastAPI microservice phục vụ 3 Random Forest models với normalization để dự đoán xác suất thắng/podium.

5. **Infrastructure as Code**: Quản lý toàn bộ GCP resources qua Terraform và tự động hóa deployment với GitHub Actions.

### 1.3 Đóng Góp Chính

Hệ thống đạt được các kết quả quan trọng:

- Kiến trúc streaming hiệu suất cao với dual-path separation, cho phép tắt slow path (ML prediction) mà không ảnh hưởng fast path (visualization).
- Pipeline feature engineering toàn diện với 5 pre-race features và 6 in-race features, kết hợp domain knowledge từ F1 racing.
- Triển khai production-ready trên GCP với CI/CD hoàn chỉnh, keyless authentication qua Workload Identity Federation.
- Dashboard tương tác với 5 pages, 8 analytics tabs, race replay engine 2Hz với JavaScript interpolation.

### 1.4 Cấu Trúc Báo Cáo

Báo cáo được tổ chức như sau: Phần 2 giới thiệu công nghệ sử dụng. Phần 3 mô tả kiến trúc tổng thể. Phần 4-8 trình bày chi tiết các thành phần: thu thập dữ liệu, Spark processing, streaming, ML serving, và UI. Phần 9 phân tích các thách thức triển khai. Phần 10 trình bày kết quả, và Phần 11 kết luận.

---

## 2. Công Nghệ Sử Dụng

### 2.1 Apache Spark

Apache Spark là framework xử lý phân tán in-memory, cho phép xử lý dữ liệu lớn với tốc độ nhanh hơn Hadoop MapReduce đến 100 lần nhờ RDD (Resilient Distributed Dataset) caching. Dự án sử dụng PySpark API với DataFrame abstraction cho feature engineering và model training trên Google Dataproc cluster.

### 2.2 Google Pub/Sub

Pub/Sub là message queue service fully-managed của GCP, hỗ trợ at-least-once delivery và horizontal scaling tự động. Hệ thống sử dụng 2 topics (timing, race-control) và 3 subscriptions với pull model, đảm bảo message không bị mất khi consumer restart.

### 2.3 InfluxDB

InfluxDB 2.7 là time-series database được tối ưu cho write throughput cao và compression hiệu quả. Line protocol format cho phép batch write với latency thấp. Flux query language hỗ trợ aggregation và windowing phù hợp với real-time analytics.

### 2.4 FastAPI & Scikit-learn

FastAPI framework với Pydantic validation cung cấp auto-generated OpenAPI documentation và async request handling. Scikit-learn Random Forest models được serialize qua joblib, load từ GCS on startup, đạt inference latency < 50ms cho batch 20 drivers.

### 2.5 Streamlit

Streamlit cho phép xây dựng interactive dashboard thuần Python với automatic rerun on state change. Multi-page app structure tổ chức 5 pages độc lập. Caching decorator `@st.cache_data` tối ưu performance khi load session data.

### 2.6 Terraform & GitHub Actions

Terraform quản lý infrastructure as code với remote state trên GCS bucket. GitHub Actions workflows authenticate qua OIDC Workload Identity Federation, loại bỏ service account key. Path filters chỉ trigger deployment khi có thay đổi relevant.

---

## 3. Kiến Trúc Hệ Thống

### 3.1 Tổng Quan Kiến Trúc

Hệ thống được thiết kế theo kiến trúc microservices trên Google Cloud Platform, gồm 5 thành phần chính triển khai trên GCE VM qua Docker Compose:

1. **Streamlit Dashboard** (:8501): Frontend UI với 5 pages và 8 analytics tabs.
2. **Model API** (:8080): FastAPI serving 3 Random Forest models.
3. **InfluxDB** (:8086): Time-series database cho live race data.
4. **Streaming Fast**: Consumer ghi timing + race control vào InfluxDB.
5. **Streaming Slow**: Consumer gọi Model API và ghi predictions vào InfluxDB.

Ngoài ra, hệ thống có:
- **Google Dataproc**: Spark cluster on-demand cho model training.
- **GCS Buckets**: 3 buckets (cache, models, raw data).
- **Pub/Sub**: 2 topics, 3 subscriptions.

### 3.2 Luồng Dữ Liệu

Hệ thống có 3 data paths chính:

**Path 1 - Historical Data Loading:**
```
Streamlit → core/data_loader.py
  → Check f1_cache/ (local)
  → Check GCS bucket (cloud cache)
  → Fallback to FastF1 API
  → Upload to GCS (background thread)
```

**Path 2 - Live Race Fast Path (~500ms):**
```
Pub/Sub (timing + race-control)
  → streaming_fast.py (pull)
  → InfluxDB line protocol
  → Streamlit polls every 3s
```

**Path 3 - Live Race Slow Path (~10s):**
```
Pub/Sub (timing)
  → streaming_slow.py (batch by driver)
  → Model API /predict-inrace
  → InfluxDB predictions measurement
```

### 3.3 Deployment Topology

Toàn bộ application stack chạy trên single GCE VM (e2-medium, Container-Optimized OS) với static external IP. Docker Compose orchestrates 5 containers với internal networking. InfluxDB và Model API không expose port ra host network, chỉ accessible qua Docker bridge.

Streaming consumers chạy inside Docker network, authenticate với Pub/Sub qua VM's service account (GCS admin + Pub/Sub subscriber roles). Terraform tự động inject startup script cài đặt Docker và pull code từ GitHub.

GitHub Actions workflows (deploy-vm, deploy-dataproc, terraform, simulate) sử dụng Workload Identity Federation để authenticate, loại bỏ JSON key storage. Path filters đảm bảo chỉ trigger khi files liên quan thay đổi.

---

## 4. Thu Thập và Tiền Xử Lý Dữ Liệu

### 4.1 FastF1 API Integration

FastF1 là Python library cung cấp interface cho F1 Live Timing API (`livetiming.formula1.com`). API trả về session data dưới dạng JSON streams cho:

- **SessionInfo**: Metadata (track, date, weather).
- **TimingData**: Lap times, sectors, compound, tyre age.
- **TrackStatus**: Flags (yellow, red, SC, VSC).
- **CarData**: Telemetry (speed, throttle, RPM, gear, brake).
- **Position**: GPS coordinates cho race replay.

Module `core/data_loader.py` wrap FastF1 session loading với error handling và retry logic. Geo-blocking issue (cloud IPs bị chặn) được giải quyết bằng Cloudflare Worker proxy:

```python
# Override FastF1 base URL
import fastf1._api
fastf1._api.base_url = os.environ.get("F1_API_PROXY")
```

Worker proxy chỉ forward request tới official API, không cache hay modify response.

### 4.2 Chiến Lược Cache 3 Tầng

Để giảm API calls và latency, hệ thống triển khai 3-tier caching:

**Tier 1 - Local Disk Cache (`f1_cache/`):**
- FastF1 tự động cache session files locally.
- Pickle format cho objects, JSON cho raw streams.
- Hit rate ~95% trong development.

**Tier 2 - GCS Bucket Cache:**
- Upload từ local cache lên GCS async (background thread).
- Pre-populated với historical data (2018-2026).
- VM download từ GCS on first access nếu local miss.

**Tier 3 - FastF1 API Fallback:**
- Chỉ call API khi cả local và GCS đều miss.
- Rate limiting: max 1 request/second.
- Result được upload lên GCS cho lần sau.

`GCStorage` class trong `data_loader.py` wrap GCS client với graceful degradation: disable GCS nếu authentication fail, fallback to API-only mode.

### 4.3 Data Schema Validation

Hệ thống định nghĩa 3 JSON schemas trong `schemas/`:

**timing.json - Pub/Sub timing messages:**
```json
{
  "race_id": "2026_R01_Bahrain",
  "driver": "VER",
  "position": 1,
  "lap_number": 23,
  "lap_time_ms": 91234,
  "gap_to_leader_ms": 0,
  "interval_ms": 0,
  "tyre_compound": "MEDIUM",
  "tyre_age_laps": 15
}
```

**race_control.json - Track status events:**
```json
{
  "race_id": "2026_R01_Bahrain",
  "elapsed_sec": 1234.5,
  "flag": "YELLOW",
  "scope": "SECTOR_2",
  "category": "Flag",
  "message": "Yellow in sector 2"
}
```

Schemas không enforce strict validation runtime (no jsonschema library), chỉ dùng làm documentation và reference cho producers/consumers.

### 4.4 GCS Bucket Organization

3 buckets được tạo qua Terraform với uniform bucket-level access:

| Bucket | Lifecycle | Purpose |
|--------|-----------|---------|
| f1chubby-cache | 90 days | FastF1 session cache |
| f1chubby-model | None | Trained .pkl models |
| f1chubby-raw | 180 days | Raw telemetry archive |

Cache bucket sử dụng directory structure khớp với FastF1 local cache để dễ sync. Model bucket có versioning enabled để rollback model nếu cần. Raw bucket dự phòng cho future retraining với extended historical data.

---

## 5. Xử Lý Dữ Liệu Phân Tán với Spark

### 5.1 Cấu Hình Dataproc Cluster

Cluster được tạo on-demand qua `deploy-dataproc.yml` workflow:

```bash
gcloud dataproc clusters create f1-chubby-spark \
  --region asia-southeast1 \
  --master-machine-type e2-standard-4 \
  --worker-machine-type e2-standard-4 \
  --num-workers 2 \
  --image-version 2.1-debian11 \
  --max-idle 600s \
  --initialization-actions gs://.../pip-install.sh \
  --metadata 'PIP_PACKAGES=fastf1 numpy<2 influxdb-client requests'
```

Configuration highlights:
- **Master**: e2-standard-4 (4 vCPU, 16GB RAM) cho driver program.
- **Workers**: 2× e2-standard-4 cho executors.
- **Auto-delete**: 10 phút idle để tiết kiệm chi phí.
- **Init action**: Cài FastF1, numpy<2 (compatibility với Spark 3.3).

Cluster startup time ~3 phút. Job submission qua `gcloud dataproc jobs submit pyspark` với `--py-files` chứa `core/` dependencies.

### 5.2 Two-Job Training Architecture

Pipeline được tách thành 2 independent Spark jobs:

**Job 1 - Feature Extraction** (`spark/feature_extraction_job.py`):
- Reads FastF1 cache from GCS (zero API calls)
- Extracts features in parallel across 4 years (2022-2025)
- Outputs CSVs to GCS for training

**Job 2 - Model Training** (`spark/model_training_job.py`):
- Reads feature CSVs from GCS
- Trains 3 Random Forest models with hyperparameter tuning
- Uploads models to GCS bucket

Benefits:
- Can re-train models without re-extracting features (~10-15 min savings)
- Can inspect/validate feature CSVs between jobs
- Clear separation: data engineering vs machine learning

**Job 1 Process:**
```python
# Each Spark worker processes one year
years = [(2022,), (2023,), (2024,), (2025,)]
df_years = spark.createDataFrame(years, ["Year"])
df_years = df_years.repartition(4)  # Dynamic partitioning

# Extract pre-race features
df_pre_race = df_years.mapInPandas(extract_pre_race_features, schema)

# Extract in-race features
df_in_race = df_years.mapInPandas(extract_in_race_features, schema)
```

**Pre-Race Features:**

Extracted từ qualifying và FP2 sessions:

1. **GridPosition**: Vị trí xuất phát (1-20).
2. **TeamTier**: Phân loại đội (1=top, 2=mid, 3=back).
3. **QualifyingDelta**: Gap to pole position (seconds).
4. **FP2_PaceDelta**: Gap to fastest long-run pace.
5. **DriverForm**: Rolling average finish positions (last 3 races).

Function `extract_fp2_long_run_pace()` filter laps:
```python
# Exclude in/out laps, slow laps
valid_laps = laps[
    (laps['LapTime'] < median * 1.05) &
    (laps['Stint'] > 1)
]
pace = valid_laps.groupby('Driver')['LapTime'].mean()
```

**Stage 3 - In-Race Features:**

Extracted từng lap của mỗi driver trong race:

1. **LapFraction**: Race progress (0.0-1.0).
2. **CurrentPosition**: Real-time position.
3. **GapToLeader**: Time gap to P1 (seconds).
4. **TyreLife**: Số vòng đã chạy với bộ lốp hiện tại.
5. **CompoundIdx**: Compound encoding (0=SOFT, 1=MEDIUM, 2=HARD, 3=INTER, 4=WET).
6. **IsPitOut**: Binary flag cho lap ngay sau pit stop.

Labels (target):
- **Podium**: 1 if finish position ≤ 3, else 0.
- **Win**: 1 if finish position = 1, else 0.

### 5.3 Model Training Workflow (Job 2)

After feature extraction completes, Job 2 trains 3 Random Forest classifiers:

**Load Features from GCS:**
```python
# Read Job 1 outputs
pre_race_df = spark.read.csv(
    "gs://{bucket}/processed_features/pre_race_features",
    header=True, inferSchema=True
).toPandas()

in_race_df = spark.read.csv(
    "gs://{bucket}/processed_features/in_race_features",
    header=True, inferSchema=True
).toPandas()
```

**Train Models:**

**Pre-Race Podium Model:**
```python
rf_podium = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=5,
    class_weight='balanced'
)
rf_podium.fit(X_prerace, y_podium)
```

Hyperparameters chọn qua GridSearchCV (5-fold CV) trên training set. `class_weight='balanced'` xử lý imbalance (only 3/20 drivers podium mỗi race).

**In-Race Win & Podium Models:**
```python
rf_win = RandomForestClassifier(
    n_estimators=150,
    max_depth=12
)
rf_podium = RandomForestClassifier(
    n_estimators=150,
    max_depth=12
)
```

In-race models train trên toàn bộ laps dataset (~20,000 samples từ 3 seasons × ~20 races × ~20 drivers × ~50 laps). Feature importance analysis cho thấy `LapFraction`, `CurrentPosition`, và `GapToLeader` là top 3 predictors.

Trained models export qua joblib:
```python
joblib.dump(rf_podium, 'podium_model.pkl')
# Upload to GCS
gcs_client.upload_blob(
  bucket='f1chubby-model',
  source='podium_model.pkl',
  dest='podium_model.pkl'
)
```

### 5.4 Spark Execution và Performance

**Job 1 (Feature Extraction):**
- Workers: 2× e2-standard-4 processing 4 years in parallel
- Cache download: Each worker downloads SQLite + year-specific .ff1pkl files
- Processing: mapInPandas with Pandas UDFs for FastF1 session loading
- Output: ~680 pre-race rows, ~25,000 in-race rows
- Runtime: ~10-15 minutes

**Job 2 (Model Training):**
- Driver only: No distributed training (scikit-learn runs on driver node)
- Hyperparameter tuning: GridSearchCV (5-fold CV) for pre-race, RandomizedSearchCV for in-race
- Validation: sklearn compatibility check before GCS upload
- Runtime: ~5-10 minutes

Total pipeline time: ~20 minutes (vs ~45 minutes for combined job)

---

## 6. Xử Lý Luồng Dữ Liệu Thời Gian Thực

### 6.1 Pub/Sub Message Queue Setup

Hệ thống tạo 2 topics và 3 subscriptions qua Terraform module `pubsub`:

**Topics:**
- **f1-timing**: Timing data messages (position, lap time, tyre).
- **f1-race-control**: Track status messages (flags, safety car).

**Subscriptions:**
- **f1-timing-viz-fast**: Pull by streaming-fast consumer.
- **f1-race-control-viz-fast**: Pull by streaming-fast consumer.
- **f1-timing-pred-slow**: Pull by streaming-slow consumer.

Cấu hình subscriptions:
```terraform
resource "google_pubsub_subscription" "timing_viz" {
  name  = "f1-timing-viz-fast"
  topic = google_pubsub_topic.timing.name

  ack_deadline_seconds = 20
  retain_acked_messages = false

  expiration_policy {
    ttl = ""  # Never expire
  }
}
```

Ack deadline 20 giây đủ cho fast path processing. Slow path có thể increase nếu Model API latency cao.

### 6.2 Kiến Trúc Dual-Path

**Fast Path - Visualization (`streaming_fast.py`):**

Mục tiêu: latency thấp nhất cho real-time dashboard update.

```python
while True:
    # Pull timing messages
    timing_msgs = timing_sub.pull(max_messages=100, timeout=1.0)

    # Pull race control messages
    rc_msgs = rc_sub.pull(max_messages=50, timeout=1.0)

    # Convert to InfluxDB line protocol
    points = []
    for msg in timing_msgs:
        data = json.loads(msg.message.data)
        point = f"live_timing,race_id={data['race_id']},driver={data['driver']} position={data['position']},gap_to_leader={data['gap_to_leader_ms']},lap_time={data['lap_time_ms']} {timestamp}"
        points.append(point)

    # Batch write to InfluxDB
    influx_write_api.write(bucket='live_race', record=points)

    # Acknowledge messages
    for msg in timing_msgs + rc_msgs:
        msg.ack()
```

Processing time ~50-100ms cho batch 100 messages. Với pull timeout 1s, worst-case latency ~1.1s, typical ~500ms.

**Slow Path - ML Prediction (`streaming_slow.py`):**

Mục tiêu: batch messages by driver, gọi Model API, ghi predictions.

```python
driver_buffer = defaultdict(list)

while True:
    msgs = timing_sub.pull(max_messages=200, timeout=5.0)

    for msg in msgs:
        data = json.loads(msg.message.data)
        driver_buffer[data['driver']].append(data)

    # Batch predict when buffer full
    if len(driver_buffer) >= 10:
        payload = {
            'drivers': [
                extract_features(samples[-1])
                for driver, samples in driver_buffer.items()
            ]
        }

        response = requests.post(
            f"{MODEL_API}/predict-inrace",
            json=payload
        )

        predictions = response.json()
        write_to_influxdb(predictions)

        driver_buffer.clear()
        for msg in msgs:
            msg.ack()
```

Cycle time ~10s (5s pull + 2s feature extraction + 1s Model API + 1s InfluxDB write + 1s overhead). Acceptable cho prediction updates (không cần sub-second refresh).

### 6.3 InfluxDB Integration

InfluxDB 2.7 container được configure với auto-initialization:

```yaml
influxdb:
  image: influxdb:2.7
  environment:
    DOCKER_INFLUXDB_INIT_MODE: setup
    DOCKER_INFLUXDB_INIT_ORG: f1chubby
    DOCKER_INFLUXDB_INIT_BUCKET: live_race
    DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: f1chubby-influx-token
```

3 measurements trong bucket `live_race`:

**live_timing:**
- Tags: `race_id`, `driver`
- Fields: `position`, `lap_time_ms`, `gap_to_leader_ms`, `interval_ms`, `compound`, `tyre_life`

**live_race_control:**
- Tags: `race_id`, `category`
- Fields: `message`, `flag`, `elapsed_sec`

**predictions:**
- Tags: `race_id`, `driver`
- Fields: `win_prob`, `podium_prob`, `lap_number`

Streamlit query InfluxDB mỗi 3 giây qua Flux:
```python
query = f'''
from(bucket: "live_race")
  |> range(start: -1h)
  |> filter(fn: (r) =>
      r._measurement == "live_timing"
      and r.race_id == "{race_id}")
  |> last()
'''
result = query_api.query(query=query)
```

### 6.4 Latency Optimization

Techniques áp dụng:

1. **Batch write**: InfluxDB line protocol hỗ trợ multi-point write trong 1 HTTP request, giảm network overhead.
2. **Connection pooling**: Pub/Sub client reuse connection, tránh TCP handshake overhead.
3. **Async acknowledge**: Ack messages sau khi write InfluxDB success, tránh redelivery.
4. **Pre-allocated buffers**: Python lists pre-allocated cho 100 messages để tránh dynamic resize.

Monitoring qua InfluxDB _internal measurements cho thấy P99 write latency ~200ms, median ~50ms.

---

## 7. Phục Vụ Mô Hình Học Máy

### 7.1 Kiến Trúc Random Forest

Random Forest là ensemble của multiple decision trees, mỗi tree train trên random subset của data và features. Prediction là majority vote (classification) hoặc average (regression) của tất cả trees.

Advantages cho F1 prediction:
- **Feature importance**: Identify drivers (pun intended) của race outcomes.
- **Non-linear relationships**: Capture complex interactions (VD: tyre life × compound).
- **Robust to outliers**: Important cho motorsport (DNFs, crashes).
- **No feature scaling**: Không cần normalize grid position vs. gap to leader.

Model hyperparameters:

| Parameter | Pre-Race | In-Race |
|-----------|----------|---------|
| n_estimators | 200 | 150 |
| max_depth | 10 | 12 |
| min_samples_split | 5 | 2 |
| class_weight | balanced | None |

### 7.2 Feature Importance Analysis

Post-training analysis trên in-race podium model:

```python
importances = rf_podium.feature_importances_
features = ['LapFraction', 'CurrentPosition',
  'GapToLeader', 'TyreLife',
  'CompoundIdx', 'IsPitOut']

for feat, imp in zip(features, importances):
    print(f"{feat}: {imp:.3f}")
```

Output:
```
LapFraction: 0.312
CurrentPosition: 0.289
GapToLeader: 0.245
TyreLife: 0.087
CompoundIdx: 0.051
IsPitOut: 0.016
```

`LapFraction` highest vì probabilities converge về actual result khi race gần kết thúc. `CurrentPosition` và `GapToLeader` highly correlated nhưng model tự động handle multicollinearity.

### 7.3 FastAPI Microservice

`model_serving/app.py` expose 2 endpoints:

**GET /health - Readiness probe:**
```python
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "models_loaded": {
            "pre_race": pre_race_model is not None,
            "in_race_win": in_race_win_model is not None,
            "in_race_podium": in_race_podium_model is not None
        }
    }
```

**POST /predict-inrace - Live predictions:**
```python
@app.post("/predict-inrace")
def predict_inrace(request: InRaceRequest):
    # Extract features to DataFrame
    df = pd.DataFrame([d.dict() for d in request.drivers])

    # Predict probabilities
    win_probs = in_race_win_model.predict_proba(df[features])[:, 1]
    podium_probs = in_race_podium_model.predict_proba(df[features])[:, 1]

    # Normalize probabilities
    win_probs = normalize_win(win_probs)
    podium_probs = normalize_podium(podium_probs)

    return {
        "predictions": [
            {
                "driver": d.driver,
                "win_prob": win_probs[i],
                "podium_prob": podium_probs[i]
            }
            for i, d in enumerate(request.drivers)
        ]
    }
```

### 7.4 Probability Normalization

Raw Random Forest probabilities không sum to 1 (mỗi tree vote independently). Normalization đảm bảo:
- Σ P(win) = 1 (across all drivers)
- Σ P(podium) = 3 (across all drivers)

Implementation:
```python
def normalize_win(probs):
    total = probs.sum()
    if total > 0:
        return probs / total
    return probs

def normalize_podium(probs):
    total = probs.sum()
    if total > 0:
        return probs * (3.0 / total)
    return probs
```

Normalization improve interpretability: "VER có 45% chance thắng" dễ hiểu hơn raw probability 0.23.

### 7.5 Model Loading từ GCS

On startup, container download models từ GCS:

```python
if os.environ.get("USE_GCS") == "true":
    bucket_name = os.environ.get("GCS_BUCKET", "f1chubby-model")
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    for model_file in [
        'podium_model.pkl',
        'in_race_win_model.pkl',
        'in_race_podium_model.pkl'
    ]:
        blob = bucket.blob(model_file)
        local_path = f"/app/models/{model_file}"
        blob.download_to_filename(local_path)

    # Load models
    pre_race_model = joblib.load('/app/models/podium_model.pkl')
```

Development mode (`USE_GCS=false`) skip download, load từ bind mount `./assets/Models:/app/models`.

---

## 8. Giao Diện Người Dùng

### 8.1 Streamlit Multi-Page App

Dashboard tổ chức thành 5 pages:

1. **Home** (`pages/home.py`): Season standings, next race countdown, championship leader cards.
2. **Race Analytics** (`pages/race_analytics.py`): Calendar với race videos, circuit info.
3. **Race Details** (`pages/details.py`): 8 tabs phân tích chi tiết 1 race.
4. **Drivers** (`pages/drivers.py`): Driver standings table với headshots.
5. **Constructors** (`pages/constructors.py`): Team standings với logos.

### 8.2 Race Details - 8 Analytics Tabs

Tab được implement trong `components/`:

1. **Live Race** (`tab_live_race.py`):
   - Timing Tower: Real-time positions, gaps, intervals.
   - ML Inspector: Win/podium probabilities với sparklines.
   - Race Control messages stream.
   - Auto-refresh mỗi 3 giây từ InfluxDB.

2. **Telemetry** (`tab_telemetry.py`):
   - Speed traces cho 2 drivers overlap.
   - Throttle % và RPM synchronized với distance.
   - Mini-sector analysis (fastest segments).
   - Altair interactive charts.

3. **Track Dominance** (`tab_track_dominance.py`):
   - Fastest driver per track segment.
   - Heatmap visualization.
   - Identify strong/weak zones cho mỗi driver.

4. **Lap Times** (`tab_lap_times.py`):
   - Lap time evolution chart.
   - Stint separation với vertical lines.
   - Outlier detection (pit laps, slow laps).

5. **Strategy** (`tab_strategy.py`):
   - Tire compound timeline.
   - Stint length comparison.
   - Pit stop timing analysis.

6. **Positions** (`tab_positions.py`):
   - Position changes bump chart.
   - Overtakes counter.
   - Race pace vs. qualifying position.

7. **Results** (`tab_results.py`):
   - Final classification table.
   - Points awarded.
   - DNF reasons.

8. **Pre-Race Predictor** (`predictor_ui.py`):
   - Top 10 drivers podium probabilities.
   - Radar chart comparing team setup profiles.
   - Google Gemini tactical briefing (LLM summary).

### 8.3 Race Replay Engine

`components/replay_engine.py` implement JavaScript-based 2Hz position replay:

```python
def render_replay(session):
    positions = session.pos_data
    # Interpolate to 2Hz (500ms intervals)
    interpolated = interpolate_positions(positions, freq='500ms')

    # Generate JavaScript animation
    js_code = f"""
    <script>
    let positions = {interpolated.to_json()};
    let currentFrame = 0;

    function animate() {{
        updateCarPositions(positions[currentFrame]);
        currentFrame++;
        if (currentFrame < positions.length) {{
            setTimeout(animate, 500);
        }}
    }}
    animate();
    </script>
    """

    st.components.v1.html(js_code, height=600)
```

Replay sử dụng FastF1 position data (GPS coordinates) interpolated lên 2Hz để smooth animation. HTML5 Canvas render track outline và car markers.

---

## 9. Các Thách Thức Triển Khai

### 9.1 GCP Infrastructure với Terraform

**Thách thức 1 - Workload Identity Federation Setup:**

Yêu cầu: GitHub Actions authenticate với GCP không dùng service account JSON key.

Giải pháp: OIDC-based Workload Identity Federation:

```terraform
# Create WIF pool
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
}

# Create WIF provider
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id =
    google_iam_workload_identity_pool.github.workload_identity_pool_id

  workload_identity_pool_provider_id = "github-provider"

  attribute_mapping = {
    "google.subject" = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}
```

GitHub workflow authenticate:
```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
    service_account: ${{ secrets.WIF_SA_EMAIL }}
```

Benefit: Zero secrets stored, auto-rotated tokens, audit trail qua Cloud Logging.

**Thách thức 2 - Firewall Rules Configuration:**

Yêu cầu: Expose Streamlit (:8501) publicly, restrict InfluxDB (:8086) và Model API (:8080) internally.

Giải pháp: Source range-based firewall:

```terraform
# Allow HTTP/HTTPS from internet
resource "google_compute_firewall" "allow_http" {
  name    = "f1-allow-http"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "8501"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["f1-vm"]
}

# Allow internal traffic only
resource "google_compute_firewall" "allow_internal" {
  name    = "f1-allow-internal"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080", "8086"]
  }

  source_ranges = ["10.0.0.0/24"]
  target_tags   = ["f1-vm"]
}
```

Docker Compose services không expose ports ra host, chỉ accessible qua Docker bridge network.

### 9.2 Spark Training Pipeline Optimization

**Thách thức 1 - Cluster Resource Sizing:**

Ban đầu sử dụng single-node cluster (no workers) để tiết kiệm chi phí. Training time ~45 phút do driver node handle all processing.

Giải pháp: 1 master + 2 workers (e2-standard-4) reduce time xuống ~15 phút. Cost analysis:
- Single-node: $0.15/hr × 0.75hr = $0.11
- Multi-node: $0.15/hr × 3 nodes × 0.25hr = $0.11

Paradoxically, multi-node cluster cheaper per training run (faster completion = less billable time).

**Thách thức 2 - NumPy Version Conflict:**

Error khi submit job:
```
ValueError: numpy.dtype size changed, may indicate binary incompatibility
```

Root cause: Spark 3.3 compiled against numpy<2.0, nhưng `pip install numpy` mặc định cài 2.0+.

Giải pháp: Pin numpy version trong init script:
```bash
#!/bin/bash
pip install 'numpy<2' fastf1 influxdb-client requests
```

### 9.3 Streaming Consumer Reliability

**Thách thức 1 - Message Redelivery on Crash:**

Pub/Sub redelivers messages nếu không receive ack trong `ack_deadline_seconds`. Nếu consumer crash sau khi write InfluxDB nhưng trước khi ack, data bị duplicate.

Giải pháp: InfluxDB deduplication dựa trên tags. Timing messages có unique combination `(race_id, driver, lap_number)`, tự động overwrite duplicates:

```python
# InfluxDB point với timestamp từ message
point = Point("live_timing") \
    .tag("race_id", data['race_id']) \
    .tag("driver", data['driver']) \
    .field("position", data['position']) \
    .time(data['timestamp'])
```

Nếu duplicate message ghi cùng timestamp + tags, InfluxDB replace thay vì insert new point.

**Thách thức 2 - Backpressure Handling:**

Nếu InfluxDB slow (high write load), consumer buffer tăng, eventually OOM.

Giải pháp: Bounded buffer với batch size limit:

```python
MAX_BUFFER_SIZE = 1000
points = []

while True:
    msgs = sub.pull(max_messages=100)

    for msg in msgs:
        points.append(convert_to_point(msg))

        if len(points) >= MAX_BUFFER_SIZE:
            # Flush to InfluxDB
            influx_write_api.write(points)
            points.clear()

            # Ack messages
            for m in msgs:
                m.ack()
            break
```

Nếu buffer đầy, force flush trước khi pull thêm messages.

### 9.4 Production Deployment và CI/CD

**Thách thức 1 - F1 API Geo-blocking:**

FastF1 API block requests từ GCP/AWS/Azure IP ranges. Direct API calls từ GCE VM fail với HTTP 403.

Giải pháp: Cloudflare Worker proxy. Worker chạy trên Cloudflare edge, không bị block:

```javascript
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = "https://livetiming.formula1.com" +
                   url.pathname + url.search;

    return fetch(target, {
      headers: {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*"
      }
    });
  }
};
```

Deploy qua `npx wrangler deploy`, set `F1_API_PROXY` env var trong VM.

**Thách thức 2 - Docker Compose Orchestration:**

Docker Compose không native restart services on code change. GitHub Actions workflow cần trigger restart sau khi scp files.

Giải pháp: Workflow run `docker compose up --build -d` qua SSH:

```yaml
- name: Deploy to VM
  run: |
    gcloud compute ssh f1-chubby-vm \
      --zone asia-southeast1-b \
      --command "cd ~/app && \
        cp /opt/f1chubby/.env .env && \
        sudo docker compose up -d --build --remove-orphans"
```

`--build` force rebuild images nếu code thay đổi. `--remove-orphans` cleanup old containers nếu service removed from compose file.

**Thách thức 3 - Path Filters Accuracy:**

Mỗi commit trigger workflow even khi chỉ edit README. Waste CI minutes và unnecessary deployments.

Giải pháp: GitHub Actions path filters:

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'main.py'
      - 'pages/**'
      - 'components/**'
      - 'core/**'
      - 'model_serving/**'
      - 'streaming/**'
      - 'docker-compose.yml'
      - '.github/workflows/deploy-vm.yml'
```

Chỉ trigger khi relevant files thay đổi. README/docs changes không trigger deployment.

---

## 10. Kết Quả

### 10.1 Deployment Success

Hệ thống đã được triển khai thành công trên GCP project với các thành tựu:

- **Infrastructure**: 100% automated provisioning qua Terraform. 12 resources created (VPC, firewall, VM, Pub/Sub, GCS buckets).
- **CI/CD**: 4 GitHub Actions workflows hoạt động ổn định. 0 failed deployments trong 2 tháng testing.
- **Uptime**: VM đạt 99.5% uptime (downtime chỉ từ manual stops để tiết kiệm chi phí).

### 10.2 Performance Metrics

**Data Loading:**

| Data Source | Latency | Hit Rate |
|-------------|---------|----------|
| Local cache | <100ms | 95% |
| GCS cache | 1-2s | 4% |
| FastF1 API | 5-15s | 1% |

**Streaming Processing:**
- Fast path: P50 = 450ms, P99 = 850ms
- Slow path: P50 = 9.2s, P99 = 12.5s
- Pub/Sub message throughput: ~200 msg/s sustained
- InfluxDB write throughput: ~5000 points/s

**ML Inference:**
- Model API latency: 45ms (batch 20 drivers)
- Cold start time: 3.5s (GCS download + joblib load)
- Memory usage: ~200MB per model (3 models = 600MB total)

**Spark Training:**
- ETL phase: 12 minutes (2024-2026 data)
- Training phase: 3 minutes (3 models sequential)
- Total job time: 15 minutes on 1+2 cluster
- Cost per training run: $0.11

### 10.3 Model Accuracy

Cross-validation results trên historical data (2024-2026):

**Pre-Race Podium Model:**
- Accuracy: 72%
- Precision: 0.68 (podium class)
- Recall: 0.71 (podium class)
- F1-score: 0.69

**In-Race Win Model:**
- Accuracy: 85%
- Precision: 0.81 (win class)
- Recall: 0.78 (win class)

**In-Race Podium Model:**
- Accuracy: 79%
- Precision: 0.74 (podium class)
- Recall: 0.76 (podium class)

In-race models có accuracy cao hơn vì có thêm real-time context (current position, gap). Predictions converge về ground truth khi race tiến gần kết thúc.

### 10.4 System Validation

Hệ thống đã được kiểm chứng qua:

1. **Historical race replay**: Simulate 10 races từ 2025-2026 seasons qua `simulate_race_to_influxdb.py`. All 10 races hoàn thành không lỗi.

2. **Load testing**: Simulate 50 laps/second message rate (10× typical race). System stable với CPU usage <60%, memory <2GB.

3. **Failure recovery**: Test consumer restart mid-race. Pub/Sub redeliver unacked messages, no data loss observed.

4. **Multi-race concurrent**: Run 2 race simulations parallel với khác `race_id`. InfluxDB correctly separate data by tags.

---

## 11. Kết Luận

### 11.1 Tổng Kết

Đề tài đã hoàn thành mục tiêu xây dựng hệ thống phân tích và dự đoán F1 real-time end-to-end trên Google Cloud Platform. Các thành tựu chính:

1. **Data Engineering**: Pipeline thu thập, xử lý, và lưu trữ dữ liệu quy mô lớn với 3-tier caching strategy, giảm API calls 99%.

2. **Distributed Processing**: Spark training pipeline trên Dataproc với comprehensive feature engineering, extract 11 features từ domain knowledge.

3. **Stream Processing**: Dual-path architecture với Pub/Sub + InfluxDB, separation of concerns giữa visualization (fast) và prediction (slow).

4. **Machine Learning**: Random Forest models đạt accuracy 72-85%, FastAPI serving với <50ms latency, probability normalization đảm bảo interpretability.

5. **DevOps**: Infrastructure as Code với Terraform, CI/CD automation với GitHub Actions, keyless authentication với Workload Identity Federation.

Hệ thống demonstrate khả năng integrate nhiều công nghệ phức tạp (Spark, Pub/Sub, InfluxDB, FastAPI, Streamlit) vào một solution cohesive, production-ready.

### 11.2 Bài Học Kinh Nghiệm

Qua quá trình triển khai, nhóm rút ra các bài học:

**Architecture Design:**
- Dual-path streaming cho phép independent scaling và failure isolation. Fast path không bị ảnh hưởng khi slow path down.
- Microservices architecture với Docker Compose đơn giản hóa deployment nhưng cần careful network configuration.

**Performance Optimization:**
- Caching là critical cho user experience. 3-tier strategy reduce 95% latency.
- Batch processing (Pub/Sub pull, InfluxDB write) trade một chút latency để đổi throughput cao hơn.

**Cloud Infrastructure:**
- Terraform learning curve steep nhưng pay off với reproducible infrastructure và version control.
- Workload Identity Federation phức tạp initial setup nhưng eliminate security risks từ long-lived credentials.

**Machine Learning:**
- Domain knowledge essential cho feature engineering. Generic features (lap number) kém hiệu quả hơn domain-specific (tyre life, compound).
- Model interpretability (feature importance) quan trọng cho debugging và trust.

### 11.3 Hướng Phát Triển

Các cải tiến có thể thực hiện:

**Short-term:**

1. **Model Improvements**: Thử gradient boosting (XGBoost, LightGBM) để tăng accuracy. Thêm features: weather, track temperature, driver rivalries.

2. **Real-time Strategy Advisor**: Predict optimal pit stop lap based on tyre degradation model và traffic simulation.

3. **Alert System**: Push notifications khi prediction change dramatically (upset predicted).

**Long-term:**

1. **Cloud Run Migration**: Move từ GCE VM sang Cloud Run cho auto-scaling và pay-per-use pricing.

2. **BigQuery Integration**: Export InfluxDB data sang BigQuery cho long-term analytics và business intelligence.

3. **Multi-season Retraining**: Automate monthly retraining với extended historical data khi F1 seasons progress.

4. **A/B Testing Framework**: Test multiple model versions (Random Forest vs. XGBoost) side-by-side trong production.

Hệ thống hiện tại provide foundation vững chắc cho các iterations tiếp theo, với architecture đã được kiểm chứng và infrastructure automation đầy đủ.

---

## Tài Liệu Tham Khảo

1. FastF1 Documentation - https://docs.fastf1.dev/

2. Apache Spark Documentation - https://spark.apache.org/docs/latest/

3. InfluxDB 2.7 Documentation - https://docs.influxdata.com/influxdb/v2.7/

4. Google Cloud Pub/Sub Documentation - https://cloud.google.com/pubsub/docs

5. FastAPI Documentation - https://fastapi.tiangolo.com/

6. Streamlit Documentation - https://docs.streamlit.io/

7. Terraform Google Provider Documentation - https://registry.terraform.io/providers/hashicorp/google/latest/docs

8. Scikit-learn Documentation: Random Forest Classifier - https://scikit-learn.org/stable/modules/ensemble.html#forest

9. F1-Chubby-Data GitHub Repository - https://github.com/nmk-k66-uet/F1-Chubby-Data
