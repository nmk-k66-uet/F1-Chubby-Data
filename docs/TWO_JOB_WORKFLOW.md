# Model Training Pipeline

## Overview

Two-job architecture for distributed F1 model training on Google Dataproc:

**Job 1: Feature Extraction** - Reads FastF1 cache from GCS, extracts features in parallel
**Job 2: Model Training** - Trains 3 Random Forest models from extracted features

## Prerequisites

**GCS Cache** - Upload local f1_cache to GCS (one-time setup):
```bash
gsutil -m rsync -r ~/f1_cache/ gs://f1chubby-raw-{project_id}/
```

This includes session data (*.ff1pkl) and **fastf1_http_cache.sqlite** (required for zero-API operation)

## Usage

### Via GitHub Actions

**Step 1: Feature Extraction** (~10-15 min)
1. GitHub Actions → Deploy Dataproc Jobs → Run workflow
2. Select: `feature_extraction`
3. Output: `gs://{bucket}/processed_features/` (pre_race & in_race CSVs)

**Step 2: Model Training** (~5-10 min)
1. GitHub Actions → Deploy Dataproc Jobs → Run workflow
2. Select: `training`
3. Output: `gs://{model_bucket}/` (3 models + metrics)

## Benefits

- **Independent re-runs**: Re-train without re-extracting (saves ~10-15 min per iteration)
- **Feature inspection**: Validate CSVs between jobs
- **Clear debugging**: Separate logs for extraction vs training

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "No schedule for {year}" | Missing SQLite cache | Upload: `gsutil -m rsync -r ~/f1_cache/ gs://{bucket}/` |
| Zero in-race features | Cache download failed | Check Dataproc logs for "Downloaded X files" |
| "Insufficient features" | Job 1 extraction errors | Check Job 1 logs |
| "Model validation failed" | sklearn version mismatch | Verify cluster has `scikit-learn==1.7.2` |

## Manual Execution

```bash
# Job 1: Feature Extraction
gcloud dataproc jobs submit pyspark \
  gs://{staging_bucket}/spark/feature_extraction_job.py \
  --cluster f1-chubby-spark --region asia-southeast1 \
  --py-files gs://{staging_bucket}/spark/core_dependencies.zip \
  -- {project_id}

# Job 2: Model Training
gcloud dataproc jobs submit pyspark \
  gs://{staging_bucket}/spark/model_training_job.py \
  --cluster f1-chubby-spark --region asia-southeast1 \
  --py-files gs://{staging_bucket}/spark/core_dependencies.zip \
  -- {project_id}
```
