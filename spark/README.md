# Spark Jobs

PySpark jobs designed to run on **Google Dataproc**. This directory contains the two-job model training pipeline.

## Contents

| File | Description |
|------|-------------|
| `feature_extraction_job.py` | Reads FastF1 cache from GCS (2022–2025 seasons), extracts features in parallel using `mapInPandas`, saves to CSV |
| `model_training_job.py` | Trains 3 Random Forest models from extracted features with GridSearchCV/RandomizedSearchCV, validates compatibility, uploads `.pkl` to GCS |
| `training_pipeline.py` | Legacy monolithic pipeline (deprecated - use two-job workflow) |

## Two-Job Training Workflow

The training pipeline is split into two independent jobs for better debugging, faster iteration, and feature inspection.

### Job 1: Feature Extraction

**What It Does:**

1. Downloads FastF1 cache from `gs://f1chubby-raw-<project_id>/` (includes `fastf1_http_cache.sqlite` + session `.ff1pkl` files)
2. Processes 2022–2025 seasons in parallel across Spark workers (4 years = 4 partitions)
3. Extracts **pre-race features**: grid position, team tier, qualifying delta, FP2 pace delta, driver form
4. Extracts **in-race features**: lap fraction, current position, gap to leader, tyre life, compound index, pit-out flag
5. Saves features to `gs://f1chubby-raw-<project_id>/processed_features/` as CSV (pre_race + in_race)

### Job 2: Model Training

**What It Does:**

1. Reads extracted features from GCS (output of Job 1)
2. Trains 3 Random Forest classifiers with hyperparameter tuning:
   - `podium_model.pkl` — pre-race podium prediction (GridSearchCV, 5-fold CV)
   - `in_race_win_model.pkl` — live race win prediction (RandomizedSearchCV)
   - `in_race_podium_model.pkl` — live race podium prediction (RandomizedSearchCV)
3. Validates model compatibility (sklearn version check to prevent serving errors)
4. Generates metrics reports (.txt files with accuracy, classification reports, best hyperparameters)
5. Uploads `.pkl` files and metrics to `gs://f1chubby-model-<project_id>/`

### Run on Dataproc (via GitHub Actions)

The easiest way is to trigger the `deploy-dataproc.yml` workflow:

**Step 1: Feature Extraction** (~10-15 min)
1. Go to **Actions** → **Deploy Dataproc Jobs** → **Run workflow**
2. Select `feature_extraction` as the job type
3. Output: `gs://f1chubby-raw-<project_id>/processed_features/` (pre_race & in_race CSVs)

**Step 2: Model Training** (~5-10 min)
1. Go to **Actions** → **Deploy Dataproc Jobs** → **Run workflow**
2. Select `training` as the job type
3. Output: `gs://f1chubby-model-<project_id>/` (3 models + 3 metrics files)

The workflow will:
- Upload `spark/*.py` and `core/` to GCS staging bucket
- Create or reuse a Dataproc cluster (1 master + 2 workers, `e2-standard-4`, auto-deletes after 10 min idle)
- Submit the selected job as a PySpark job

**Benefits of Two-Job Workflow:**
- Re-train models without re-extracting features (saves 10-15 min per iteration)
- Inspect feature CSVs between jobs for debugging
- Clear separation of concerns (extraction errors vs. training errors)

### Run on Dataproc (manual)

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

# 1. Upload job files to GCS
gsutil cp spark/*.py gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/
zip -r core_dependencies.zip core/
gsutil cp core_dependencies.zip gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/

# 2. Ensure a Dataproc cluster exists
gcloud dataproc clusters create f1-chubby-spark \
  --region asia-southeast1 \
  --master-machine-type e2-standard-4 \
  --worker-machine-type e2-standard-4 \
  --num-workers 2 \
  --master-boot-disk-size 50GB \
  --image-version 2.1-debian11 \
  --initialization-actions gs://goog-dataproc-initialization-actions-asia-southeast1/python/pip-install.sh \
  --metadata 'PIP_PACKAGES=fastf1 numpy<2 scikit-learn==1.7.2 joblib==1.5.3 influxdb-client requests' \
  --max-idle 600s \
  --project ${PROJECT_ID} \
  --bucket f1chubby-dataproc-staging-${PROJECT_ID}

# 3. Submit Job 1: Feature Extraction
gcloud dataproc jobs submit pyspark \
  gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/feature_extraction_job.py \
  --cluster f1-chubby-spark \
  --region asia-southeast1 \
  --project ${PROJECT_ID} \
  --py-files gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/core_dependencies.zip \
  -- ${PROJECT_ID}

# 4. Submit Job 2: Model Training (after Job 1 completes)
gcloud dataproc jobs submit pyspark \
  gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/model_training_job.py \
  --cluster f1-chubby-spark \
  --region asia-southeast1 \
  --project ${PROJECT_ID} \
  --py-files gs://f1chubby-dataproc-staging-${PROJECT_ID}/spark/core_dependencies.zip \
  -- ${PROJECT_ID}
```

### Run Locally

```bash
# Prerequisites: Java 11+, PySpark, FastF1, scikit-learn
pip install pyspark fastf1 scikit-learn pandas numpy

# Run (uses local[*] Spark master)
spark-submit spark/training_pipeline.py
```

Local mode auto-detects the platform and adjusts Spark configuration. GCS authentication requires a service account JSON key at the path configured in the script.

---

← Back to [ReadMe.md](../ReadMe.md)
