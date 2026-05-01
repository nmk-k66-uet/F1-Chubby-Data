"""
Model Serving API — Decoupled inference endpoint for F1 prediction models.

Loads pre-trained models from GCS (or local fallback) and exposes REST endpoints:
  POST /predict-inrace   — live race win/podium probabilities
  POST /predict-prerace  — pre-race podium probabilities
  GET  /health           — readiness check
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import List

import numpy as np
import pandas as pd
import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model-api")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_DIR = os.environ.get("MODEL_DIR", "/app/models")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "f1chubby-model")
USE_GCS = os.environ.get("USE_GCS", "true").lower() == "true"

# Model file names (must match what's uploaded to GCS)
PRE_RACE_MODEL_FILE = "podium_model.pkl"
IN_RACE_WIN_MODEL_FILE = "in_race_win_model.pkl"
IN_RACE_PODIUM_MODEL_FILE = "in_race_podium_model.pkl"

# ---------------------------------------------------------------------------
# Global model holders
# ---------------------------------------------------------------------------
models = {
    "pre_race": None,
    "in_race_win": None,
    "in_race_podium": None,
}


def _download_from_gcs():
    """Download model artifacts from GCS bucket to local MODEL_DIR."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    os.makedirs(MODEL_DIR, exist_ok=True)
    for fname in [PRE_RACE_MODEL_FILE, IN_RACE_WIN_MODEL_FILE, IN_RACE_PODIUM_MODEL_FILE]:
        dest = os.path.join(MODEL_DIR, fname)
        if os.path.exists(dest):
            logger.info("Model already cached locally: %s", fname)
            continue
        blob = bucket.blob(fname)
        if blob.exists():
            blob.download_to_filename(dest)
            logger.info("Downloaded %s from gs://%s/%s", fname, GCS_BUCKET, fname)
        else:
            logger.warning("Model not found in GCS: %s", fname)


def _load_models():
    """Load model artifacts from MODEL_DIR into memory.

    Raises:
        RuntimeError: If any required model file is missing, causing app to fail and restart.
    """
    missing_models = []

    for key, fname in [
        ("pre_race", PRE_RACE_MODEL_FILE),
        ("in_race_win", IN_RACE_WIN_MODEL_FILE),
        ("in_race_podium", IN_RACE_PODIUM_MODEL_FILE),
    ]:
        path = os.path.join(MODEL_DIR, fname)
        if os.path.exists(path):
            models[key] = joblib.load(path)
            logger.info("Loaded model: %s from %s", key, path)
        else:
            logger.error("CRITICAL: Model file missing: %s", path)
            missing_models.append(fname)

    if missing_models:
        raise RuntimeError(
            f"Failed to load required models: {', '.join(missing_models)}. "
            f"App will restart to retry loading from GCS."
        )


# ---------------------------------------------------------------------------
# Lifespan — download + load models on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if USE_GCS:
        try:
            _download_from_gcs()
        except Exception as e:
            logger.error("GCS download failed (continuing with local): %s", e)
    _load_models()
    yield


app = FastAPI(title="F1 Model Serving API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class InRaceDriverFeatures(BaseModel):
    driver: str = ""
    LapFraction: float
    CurrentPosition: float
    GapToLeader: float
    TyreLife: float
    CompoundIdx: float
    IsPitOut: float


class InRaceRequest(BaseModel):
    drivers: List[InRaceDriverFeatures]


class PreRaceDriverFeatures(BaseModel):
    driver: str = ""
    GridPosition: float
    TeamTier: float
    QualifyingDelta: float
    FP2_PaceDelta: float
    DriverForm: float


class PreRaceRequest(BaseModel):
    drivers: List[PreRaceDriverFeatures]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    loaded = all(m is not None for m in models.values())
    status = "healthy" if loaded else "degraded"

    if not loaded:
        # Return 503 Service Unavailable if models aren't loaded
        # This will trigger health check failure and container restart
        raise HTTPException(
            status_code=503,
            detail={
                "status": status,
                "models_loaded": {k: (v is not None) for k, v in models.items()},
            }
        )

    return {
        "status": status,
        "models_loaded": {k: (v is not None) for k, v in models.items()},
    }


@app.post("/predict-inrace")
def predict_inrace(req: InRaceRequest):
    win_model = models.get("in_race_win")
    pod_model = models.get("in_race_podium")
    if win_model is None or pod_model is None:
        raise HTTPException(503, "In-race models not loaded")

    feature_cols = ["LapFraction", "CurrentPosition", "GapToLeader", "TyreLife", "CompoundIdx", "IsPitOut"]
    rows = [d.model_dump() for d in req.drivers]
    df = pd.DataFrame(rows)
    X = df[feature_cols]

    prob_win = win_model.predict_proba(X)[:, 1]
    prob_pod = pod_model.predict_proba(X)[:, 1]

    # Normalize: total win expectation = 1.0, podium = 3.0
    factor_w = 1.0 / np.sum(prob_win) if np.sum(prob_win) > 0 else 1
    factor_p = 3.0 / np.sum(prob_pod) if np.sum(prob_pod) > 0 else 1

    results = []
    for i, row in enumerate(rows):
        w = float(np.clip(prob_win[i] * factor_w, 0, 0.99))
        p = float(np.clip(prob_pod[i] * factor_p, 0, 0.99))
        w = min(w, p)  # win prob cannot exceed podium prob
        results.append({"driver": row.get("driver", ""), "win_prob": w, "podium_prob": p})

    return {"predictions": results}


@app.post("/predict-prerace")
def predict_prerace(req: PreRaceRequest):
    model = models.get("pre_race")
    if model is None:
        raise HTTPException(503, "Pre-race model not loaded")

    feature_cols = ["GridPosition", "TeamTier", "QualifyingDelta", "FP2_PaceDelta", "DriverForm"]
    rows = [d.model_dump() for d in req.drivers]
    df = pd.DataFrame(rows)
    X = df[feature_cols]

    probs = model.predict_proba(X)[:, 1]
    factor = 3.0 / np.sum(probs) if np.sum(probs) > 0 else 1

    results = []
    for i, row in enumerate(rows):
        results.append({
            "driver": row.get("driver", ""),
            "podium_prob": float(np.clip(probs[i] * factor, 0, 0.99)),
        })

    return {"predictions": results}
