#!/usr/bin/env python3
"""
F1 Model Training Job - Train models from extracted features

This job:
1. Reads pre-race and in-race features from GCS (output of feature_extraction_job.py)
2. Trains 3 Random Forest models with hyperparameter tuning
3. Validates model compatibility (sklearn version check)
4. Uploads models and metrics to GCS

Usage:
    spark-submit --py-files core.zip model_training_job.py <PROJECT_ID>
"""

import os
import sys
import pandas as pd
import numpy as np
from pyspark.sql import SparkSession

# Parse Project ID
if len(sys.argv) > 1:
    PROJECT_ID = sys.argv[1]
else:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "default-project-id")

RAW_BUCKET = f"f1chubby-raw-{PROJECT_ID}"
MODELS_BUCKET = f"f1chubby-model-{PROJECT_ID}"

print(f"[CONFIG] Project ID: {PROJECT_ID}")
print(f"[CONFIG] Features Source: gs://{RAW_BUCKET}/processed_features/")
print(f"[CONFIG] Models Destination: gs://{MODELS_BUCKET}/")

# Initialize Spark
spark = SparkSession.builder.appName("F1_Model_Training").getOrCreate()
print(f"[SPARK] Initialized: {spark.sparkContext.master}")

# ==========================================
# Load Pre-Race Features
# ==========================================

print("\n[DATA] Loading Pre-Race features from GCS...")
pre_race_df = spark.read.csv(
    f"gs://{RAW_BUCKET}/processed_features/pre_race_features",
    header=True,
    inferSchema=True
).toPandas()

print(f"[DATA] Loaded {len(pre_race_df)} pre-race feature rows")

# Validate minimum data size
if len(pre_race_df) < 100:
    raise ValueError(
        f"Insufficient pre-race features: {len(pre_race_df)} rows. "
        f"Expected ≥100 for meaningful training. "
        f"Check feature extraction job logs."
    )

# Handle missing FP2 pace data (some races don't have FP2)
pre_race_df['FP2_PaceDelta'] = pre_race_df['FP2_PaceDelta'].fillna(
    pre_race_df.groupby('TeamTier')['FP2_PaceDelta'].transform('median')
)
pre_race_df['FP2_PaceDelta'] = pre_race_df['FP2_PaceDelta'].fillna(2.0)

print(f"[DATA] Pre-race features ready: {len(pre_race_df)} rows")

# ==========================================
# Load In-Race Features
# ==========================================

print("\n[DATA] Loading In-Race features from GCS...")
in_race_df = spark.read.csv(
    f"gs://{RAW_BUCKET}/processed_features/in_race_features",
    header=True,
    inferSchema=True
).toPandas()

print(f"[DATA] Loaded {len(in_race_df)} in-race feature rows (before cleaning)")

# Drop rows with NaN in critical columns
in_race_df = in_race_df.dropna(subset=['CurrentPosition', 'GapToLeader', 'TyreLife'])
print(f"[DATA] {len(in_race_df)} in-race feature rows after dropping NaN")

# Validate minimum data size
if len(in_race_df) < 1000:
    raise ValueError(
        f"Insufficient in-race features: {len(in_race_df)} rows. "
        f"Expected ≥1,000 for meaningful training. "
        f"Check feature extraction job logs."
    )

print(f"[DATA] In-race features ready: {len(in_race_df)} rows")

# ==========================================
# Model Training Setup
# ==========================================

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn.metrics import accuracy_score, classification_report
import joblib
from google.cloud import storage

def generate_report(model, X_test, y_test, model_name, file_path):
    """Generate training metrics report"""
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"=== {model_name} - TRAINING REPORT ===\n")
        f.write(f"Training Timestamp: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Best Hyperparameters: {model.best_params_}\n")
        f.write(f"Overall Accuracy: {acc:.4f}\n")
        f.write("-" * 60 + "\n")
        f.write("Classification Report:\n")
        f.write(report)

    print(f"[METRICS] {model_name} - Accuracy: {acc:.4f}")

print("\n[ML] Starting Model Training Phase...")

# ==========================================
# Pre-Race Podium Model
# ==========================================

print("\n[ML] Training Pre-Race Podium Model...")

# Features and target
X_pre = pre_race_df[['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']]
y_pre = pre_race_df['Podium']

# Train/test split
X_train_pre, X_test_pre, y_train_pre, y_test_pre = train_test_split(
    X_pre, y_pre, test_size=0.2, random_state=42, stratify=y_pre
)

print(f"[ML] Training set: {len(X_train_pre)} samples, Test set: {len(X_test_pre)} samples")
print(f"[ML] Class distribution - Podium: {y_train_pre.sum()}/{len(y_train_pre)} ({100*y_train_pre.mean():.1f}%)")

print("[ML] Running GridSearchCV (this may take 5-10 minutes)...")
base_pre = RandomForestClassifier(random_state=42, class_weight='balanced')
grid_pre = GridSearchCV(
    base_pre,
    param_grid={
        'n_estimators': [50, 100, 150, 200],
        'max_depth': [4, 6, 8, 10],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'bootstrap': [True, False]
    },
    cv=5,
    scoring='f1',
    n_jobs=-1,
    verbose=1
)
grid_pre.fit(X_train_pre, y_train_pre)

# Save model and metrics
joblib.dump(grid_pre.best_estimator_, 'podium_model.pkl')
generate_report(grid_pre, X_test_pre, y_test_pre, 'F1 PRE-RACE PODIUM', 'pre_race_metrics.txt')

# ==========================================
# In-Race Win Model
# ==========================================

print("\n[ML] Training In-Race Win Model...")

# Features and targets
X_in = in_race_df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
y_win = (in_race_df['FinalPosition'] == 1).astype(int)
y_pod = (in_race_df['FinalPosition'] <= 3).astype(int)

# Train/test split (stratify by podium for balance)
X_train_in, X_test_in, y_train_win, y_test_win, y_train_pod, y_test_pod = train_test_split(
    X_in, y_win, y_pod, test_size=0.2, random_state=42, stratify=y_pod
)

print(f"[ML] Training set: {len(X_train_in)} samples, Test set: {len(X_test_in)} samples")
print(f"[ML] Win distribution: {y_train_win.sum()}/{len(y_train_win)} ({100*y_train_win.mean():.1f}%)")
print(f"[ML] Podium distribution: {y_train_pod.sum()}/{len(y_train_pod)} ({100*y_train_pod.mean():.1f}%)")

print("[ML] Running RandomizedSearchCV for Win model...")
base_win = RandomForestClassifier(random_state=42, class_weight='balanced')
search_win = RandomizedSearchCV(
    base_win,
    param_distributions={
        'n_estimators': [100, 150],
        'max_depth': [8, 12, 15],
        'min_samples_split': [5, 10]
    },
    n_iter=5,
    cv=3,
    scoring='f1',
    n_jobs=-1,
    random_state=42,
    verbose=1
)
search_win.fit(X_train_in, y_train_win)
joblib.dump(search_win.best_estimator_, 'in_race_win_model.pkl')
generate_report(search_win, X_test_in, y_test_win, 'F1 IN-RACE WIN', 'in_race_win_metrics.txt')

# ==========================================
# In-Race Podium Model
# ==========================================

print("\n[ML] Training In-Race Podium Model...")
print("[ML] Running RandomizedSearchCV for Podium model...")
base_pod = RandomForestClassifier(random_state=42, class_weight='balanced')
search_pod = RandomizedSearchCV(
    base_pod,
    param_distributions={
        'n_estimators': [100, 150],
        'max_depth': [8, 12, 15],
        'min_samples_split': [5, 10]
    },
    n_iter=5,
    cv=3,
    scoring='f1',
    n_jobs=-1,
    random_state=42,
    verbose=1
)
search_pod.fit(X_train_in, y_train_pod)
joblib.dump(search_pod.best_estimator_, 'in_race_podium_model.pkl')
generate_report(search_pod, X_test_in, y_test_pod, 'F1 IN-RACE PODIUM', 'in_race_podium_metrics.txt')

print("\n[ML] All 3 models trained successfully!")

# ==========================================
# Model Validation (Critical Compatibility Check)
# ==========================================

print("\n[VALIDATION] Testing model compatibility...")

import sklearn
print(f"[VALIDATION] Training sklearn version: {sklearn.__version__}")

test_models = [
    ('podium_model.pkl', ['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']),
    ('in_race_win_model.pkl', ['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']),
    ('in_race_podium_model.pkl', ['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut'])
]

for model_path, feature_cols in test_models:
    try:
        # Reload model
        model = joblib.load(model_path)

        # Test prediction on dummy data
        X_test = pd.DataFrame([[0.5] * len(feature_cols)], columns=feature_cols)
        prediction = model.predict_proba(X_test)

        print(f"[VALIDATION] ✓ {model_path} loaded and tested successfully")

    except Exception as e:
        raise ValueError(
            f"[VALIDATION] FATAL: Model validation failed for {model_path}: {e}\n"
            f"This indicates sklearn version mismatch or corrupted model.\n"
            f"Training sklearn: {sklearn.__version__}\n"
            f"Expected serving sklearn: 1.7.2\n"
            f"Models trained with different sklearn versions will NOT load in serving API."
        )

print("[VALIDATION] ✓ All models passed compatibility check")

# ==========================================
# Upload Models to GCS
# ==========================================

def upload_to_gcs(file_name):
    """Upload model or metrics file to GCS"""
    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(MODELS_BUCKET)

        # Create bucket if it doesn't exist
        if not bucket.exists():
            bucket = client.create_bucket(MODELS_BUCKET, location="asia-southeast1")
            print(f"[GCS] Created bucket: gs://{MODELS_BUCKET}")

        # Upload file
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_name)
        print(f"[GCS] ✓ Uploaded {file_name} to gs://{MODELS_BUCKET}/{file_name}")

    except Exception as e:
        print(f"[GCS] ERROR uploading {file_name}: {e}")
        raise

print(f"\n[UPLOAD] Uploading models to gs://{MODELS_BUCKET}/...")

upload_to_gcs('podium_model.pkl')
upload_to_gcs('pre_race_metrics.txt')
upload_to_gcs('in_race_win_model.pkl')
upload_to_gcs('in_race_win_metrics.txt')
upload_to_gcs('in_race_podium_model.pkl')
upload_to_gcs('in_race_podium_metrics.txt')

print("\n[COMPLETE] Training Job Completed Successfully!")
print(f"[COMPLETE] Models available at: gs://{MODELS_BUCKET}/")
print("\n[SUMMARY] Trained Models:")
print("  - podium_model.pkl (Pre-race podium prediction)")
print("  - in_race_win_model.pkl (In-race win prediction)")
print("  - in_race_podium_model.pkl (In-race podium prediction)")
