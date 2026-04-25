# Spark Jobs

PySpark jobs designed to run on **Google Dataproc**. This directory contains the model training pipeline and Spark-based versions of the streaming consumers.

## Contents

| File | Description |
|------|-------------|
| `training_pipeline.py` | Extracts pre-race and in-race features from 2024–2026 FastF1 data, trains 3 Random Forest models, uploads `.pkl` files to GCS |
| `streaming_fast.py` | Spark version of the fast streaming consumer (Pub/Sub → InfluxDB) |
| `streaming_slow.py` | Spark version of the slow streaming consumer (Pub/Sub → Model API → InfluxDB) |

> **Note:** The `streaming/` directory at the repo root contains Docker-packaged equivalents of the streaming jobs using the plain Python Pub/Sub client. Both versions consume the same Pub/Sub subscriptions and write to the same InfluxDB measurements.

## Training Pipeline

### What It Does

1. Reads historical race data from FastF1 (2024–2026 seasons) with GCS caching
2. Extracts **pre-race features**: grid position, team tier, qualifying delta, FP2 pace delta, driver form
3. Extracts **in-race features**: lap fraction, current position, gap to leader, tyre life, compound index, pit-out flag
4. Trains 3 Random Forest classifiers:
   - `podium_model.pkl` — pre-race podium prediction
   - `in_race_win_model.pkl` — live race win prediction
   - `in_race_podium_model.pkl` — live race podium prediction
5. Uploads trained `.pkl` files to `gs://f1chubby-model-<project_id>/`

### Run on Dataproc (via GitHub Actions)

The easiest way is to trigger the `deploy-dataproc.yml` workflow:

1. Go to **Actions** → **Deploy Dataproc Jobs** → **Run workflow**
2. Select `training` as the job type
3. The workflow will:
   - Upload `spark/*.py` and `core/` to GCS staging bucket
   - Create or reuse a Dataproc cluster (1 master + 2 workers, `e2-standard-4`, auto-deletes after 10 min idle)
   - Submit the training pipeline as a PySpark job

### Run on Dataproc (manual)

```bash
# 1. Upload job files to GCS
gsutil cp spark/*.py gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/spark/
zip -r core_dependencies.zip core/
gsutil cp core_dependencies.zip gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/spark/

# 2. Ensure a Dataproc cluster exists
gcloud dataproc clusters create f1-chubby-spark \
  --region asia-southeast1 \
  --single-node \
  --master-machine-type e2-standard-4 \
  --master-boot-disk-size 50GB \
  --image-version 2.1-debian11 \
  --initialization-actions gs://goog-dataproc-initialization-actions-asia-southeast1/python/pip-install.sh \
  --metadata 'PIP_PACKAGES=fastf1 numpy<2 influxdb-client requests' \
  --max-idle 600s \
  --project gen-lang-client-0314607994 \
  --bucket f1chubby-dataproc-staging-gen-lang-client-0314607994

# 3. Submit the training job
gcloud dataproc jobs submit pyspark \
  gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/spark/training_pipeline.py \
  --cluster f1-chubby-spark \
  --region asia-southeast1 \
  --project gen-lang-client-0314607994 \
  --py-files gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/spark/core_dependencies.zip
```

### Run Locally

```bash
# Prerequisites: Java 11+, PySpark, FastF1, scikit-learn
pip install pyspark fastf1 scikit-learn pandas numpy

# Run (uses local[*] Spark master)
spark-submit spark/training_pipeline.py
```

Local mode auto-detects the platform and adjusts Spark configuration. GCS authentication requires a service account JSON key at the path configured in the script.

## Streaming Jobs on Dataproc

The Spark streaming jobs (`streaming_fast.py`, `streaming_slow.py`) can be submitted to Dataproc similarly:

```bash
gcloud dataproc jobs submit pyspark \
  gs://f1chubby-dataproc-staging-gen-lang-client-0314607994/spark/streaming_fast.py \
  --cluster f1-chubby-spark \
  --region asia-southeast1 \
  --project gen-lang-client-0314607994 \
  -- --project gen-lang-client-0314607994 \
     --influxdb-url http://<VM_IP>:8086 \
     --influxdb-token f1chubby-influx-token
```

---

← Back to [ReadMe.md](../ReadMe.md)
