import os
import fastf1
import pandas as pd
from google.cloud import storage
import logging

logger = logging.getLogger(__name__)

def get_schedule(year):
    """Race schedule from FastF1."""
    try:
        schedule = fastf1.get_event_schedule(year)
        return schedule[schedule['RoundNumber'] > 0]
    except Exception:
        return pd.DataFrame()

def get_blob(schedule, year, round_num, session_type):
    sched = schedule[schedule["RoundNumber"] == round_num]
    if sched.empty:
        return None
    
    if session_type == "FP1":
        sub_event = str(list(sched["Session1Date"])[0]).split(" ")[0] + "_" + list(sched["Session1"])[0].replace(" ", "_")
    elif session_type == "FP2":
        sub_event = str(list(sched["Session2Date"])[0]).split(" ")[0] + "_" + list(sched["Session2"])[0].replace(" ", "_")
    elif session_type == "FP3":
        sub_event = str(list(sched["Session3Date"])[0]).split(" ")[0] + "_" + list(sched["Session3"])[0].replace(" ", "_")
    elif session_type == "Q":
        sub_event = str(list(sched["Session4Date"])[0]).split(" ")[0] + "_" + list(sched["Session4"])[0].replace(" ", "_")
    elif session_type == "R":
        sub_event = str(list(sched["Session5Date"])[0]).split(" ")[0] + "_" + list(sched["Session5"])[0].replace(" ", "_")
    else:
        return None

    event_date = str(list(sched["EventDate"])[0]).split(" ")[0]
    event_name = str(list(sched["EventName"])[0]).replace(" ", "_")
    blob = f"{year}/{event_date}_{event_name}/{sub_event}"
    return blob

def load_with_gcs_cache(year, round_num, session_type, telemetry, weather, messages, cache_dir):
    """
    Loads F1 data using FastF1, but syncs with a Google Cloud Storage bucket
    to prevent redundant API calls to FastF1 servers across different Spark workers.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "<PROJECT_ID>")
    gcs_bucket = os.environ.get("GCS_CACHE_BUCKET", f"f1chubby-raw-{project_id}")
    
    schedule = get_schedule(year)
    blob_prefix = get_blob(schedule, year, round_num, session_type)
    
    had_local = False
    local_blob_dir = os.path.join(cache_dir, blob_prefix) if blob_prefix else None

    # 1. Check local cache
    if local_blob_dir and os.path.isdir(local_blob_dir) and len(os.listdir(local_blob_dir)) > 0:
        had_local = True

    # 2. Pull from GCS if not in local cache
    if local_blob_dir and not had_local:
        try:
            client = storage.Client()
            bucket = client.bucket(gcs_bucket)
            blobs = list(bucket.list_blobs(prefix=blob_prefix))
            if blobs:
                for blob in blobs:
                    dest = os.path.join(cache_dir, blob.name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    blob.download_to_filename(dest)
                had_local = True
        except Exception as e:
            logger.warning(f"GCS Pull Error for {blob_prefix}: {e}")

    # 3. Load session (FastF1 uses local cache, or fetches from API)
    session = fastf1.get_session(year, round_num, session_type)
    session.load(telemetry=telemetry, weather=weather, messages=messages)

    # 4. If we fetched fresh from API, push to GCS cache for next time
    if local_blob_dir and not had_local:
        try:
            if os.path.isdir(local_blob_dir):
                client = storage.Client()
                bucket = client.bucket(gcs_bucket)
                for file in os.listdir(local_blob_dir):
                    blob = bucket.blob(blob_prefix.replace("\\", "/") + "/" + file)
                    blob.upload_from_filename(os.path.join(local_blob_dir, file), content_type="application/octet-stream")
        except Exception as e:
            logger.warning(f"GCS Push Error for {blob_prefix}: {e}")

    return session
