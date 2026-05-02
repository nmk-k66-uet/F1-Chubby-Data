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
    except Exception as e:
        print(f"[SCHEDULE] ERROR fetching schedule for {year}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
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

def load_with_gcs_cache(year, round_num, session_type, telemetry, weather, messages, cache_dir, project_id, gcs_bucket=None):
    """
    Loads F1 data using FastF1, but syncs with a Google Cloud Storage bucket
    to prevent redundant API calls to FastF1 servers across different Spark workers.

    Hybrid cache strategy with retry logic:
    1. Check local cache (fast)
    2. Pull from GCS cache if miss (may be empty on first run)
    3. Fetch from FastF1 API with retry/backoff if still miss
    4. Push to GCS for next time

    Args:
        year: Season year
        round_num: Round number
        session_type: Session type code (e.g., 'R', 'Q', 'FP2')
        telemetry: Whether to load telemetry data
        weather: Whether to load weather data
        messages: Whether to load race messages
        cache_dir: Local cache directory path
        project_id: GCP project ID (required)
        gcs_bucket: GCS bucket name (optional, defaults to f"f1chubby-raw-{project_id}")
    """
    import time

    if gcs_bucket is None:
        gcs_bucket = f"f1chubby-raw-{project_id}"

    schedule = get_schedule(year)
    blob_prefix = get_blob(schedule, year, round_num, session_type)

    had_local = False
    local_blob_dir = os.path.join(cache_dir, blob_prefix) if blob_prefix else None

    # 1. Check local cache
    if local_blob_dir and os.path.isdir(local_blob_dir) and len(os.listdir(local_blob_dir)) > 0:
        had_local = True
        logger.info(f"[GCS] Cache hit (local): {year} R{round_num} {session_type}")

    # 2. Pull from GCS if not in local cache
    if local_blob_dir and not had_local:
        try:
            client = storage.Client(project=project_id)
            bucket = client.bucket(gcs_bucket)
            blobs = list(bucket.list_blobs(prefix=blob_prefix))
            if blobs:
                logger.info(f"[GCS] Cache hit (GCS): {year} R{round_num} {session_type}, pulling {len(blobs)} files...")
                for blob in blobs:
                    dest = os.path.join(cache_dir, blob.name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    blob.download_to_filename(dest)
                had_local = True
            else:
                logger.warning(f"[GCS] Cache miss: {year} R{round_num} {session_type}")
        except Exception as e:
            logger.warning(f"[GCS] Pull error for {blob_prefix}: {e}")

    # 3. Load session (FastF1 uses local cache, or fetches from API with retry)
    MAX_RETRIES = 3
    RETRY_DELAY = 15  # seconds (conservative to respect 500 calls/hour limit)

    session = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if not had_local:
                logger.info(f"[FastF1] Fetching from API (attempt {attempt}/{MAX_RETRIES}): {year} R{round_num} {session_type}")

            session = fastf1.get_session(year, round_num, session_type)
            session.load(telemetry=telemetry, weather=weather, messages=messages)

            # Rate limiting - wait after API call (not needed for cache hits)
            if not had_local:
                time.sleep(RETRY_DELAY)
            break  # Success

        except Exception as e:
            if attempt < MAX_RETRIES:
                backoff_delay = RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff: 10s, 20s, 40s
                logger.warning(f"[FastF1] API error (attempt {attempt}/{MAX_RETRIES}): {e}")
                logger.info(f"[FastF1] Retrying in {backoff_delay}s...")
                time.sleep(backoff_delay)
            else:
                logger.error(f"[FastF1] API failed after {MAX_RETRIES} attempts for {year} R{round_num} {session_type}: {e}")
                raise RuntimeError(
                    f"Failed to load {year} R{round_num} {session_type} after {MAX_RETRIES} attempts. "
                    f"Check: (1) FastF1 API status, (2) Network connectivity, (3) Rate limits. "
                    f"Last error: {e}"
                )

    # 4. If we fetched fresh from API, push to GCS cache for next time
    if local_blob_dir and not had_local and os.path.isdir(local_blob_dir):
        try:
            client = storage.Client(project=project_id)
            bucket = client.bucket(gcs_bucket)
            files_uploaded = 0
            for file in os.listdir(local_blob_dir):
                blob = bucket.blob(blob_prefix.replace("\\", "/") + "/" + file)
                blob.upload_from_filename(os.path.join(local_blob_dir, file), content_type="application/octet-stream")
                files_uploaded += 1
            logger.info(f"[GCS] Cached {files_uploaded} files to gs://{gcs_bucket}/{blob_prefix}")
        except Exception as e:
            logger.warning(f"[GCS] Push error for {blob_prefix}: {e}")

    return session
