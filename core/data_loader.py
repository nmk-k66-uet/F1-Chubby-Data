"""
Data Loader Module - F1 Session and Event Data Retrieval

Data sources:
  - GCS bucket (f1chubby-raw) with local disk cache (f1_cache/)
  - FastF1 library for session objects, telemetry, laps

Session data is synced from GCS on first access, then served from local cache.
"""

import streamlit as st
import fastf1
import pandas as pd
import os
import logging
import threading

try:
    from google.cloud import storage as _gcs_storage
except ImportError:
    _gcs_storage = None

logger = logging.getLogger(__name__)

# ==========================================
# CACHE CONFIGURATION
# ==========================================
GCS_CACHE_BUCKET = os.environ.get("GCS_CACHE_BUCKET", "f1chubby-cache")
CACHE_DIR = 'f1_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

# Enable FastF1 caching and suppress verbose logging
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

# Override FastF1 API base URL with a proxy (e.g. Cloudflare Worker)
# to bypass geo-blocking on cloud provider IPs
_f1_proxy = os.environ.get("F1_API_PROXY")
if _f1_proxy:
    import fastf1._api
    fastf1._api.base_url = _f1_proxy.rstrip('/')
    logger.info("F1 API proxy: %s", fastf1._api.base_url)


class GCStorage:
    """Optional GCS wrapper. Disables itself after the first connection failure."""

    def __init__(self):
        self._client = None
        self._disabled = _gcs_storage is None

    @property
    def available(self):
        return not self._disabled

    @property
    def client(self):
        if self._disabled:
            raise RuntimeError("GCS is not available")
        if self._client is None:
            try:
                self._client = _gcs_storage.Client()
            except Exception as e:
                logger.warning("GCS client init failed (disabling GCS): %s", e)
                self._disabled = True
                raise RuntimeError("GCS is not available") from e
        return self._client

    def get_bucket(self, bucket_name):
        return self.client.get_bucket(bucket_name)

    def list_buckets(self):
        buckets = self.client.list_buckets()
        return [bucket.name for bucket in buckets]

    def upload_file(self, bucket_name, blob_destination, file_path, content_type = "application/octet-stream"):
        logger.info("Upload %s to GCS", file_path)
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_destination)
        blob.upload_from_filename(file_path, content_type="application/octet-stream")
        return blob

    def list_blobs(self, bucket_name, prefix=None):
        return self.client.list_blobs(bucket_name, prefix=prefix)

    def check_blob_exists(self, bucket_name, blob_name):
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()

    def download_blob(self, bucket_name, source_blob_name):
        """Downloads blobs matching the prefix from the bucket."""
        for blob in self.list_blobs(bucket_name, prefix=source_blob_name):
            dest = os.path.join(CACHE_DIR, blob.name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if not os.path.exists(dest):
                logger.info("Download %s from GCS", blob.name)
                blob.download_to_filename(dest)

    def download_one_file(self, bucket_name, blob_file, destination_file):
        blobs = self.list_blobs(bucket_name)

        for blob in blobs:
            if blob_file in blob.name:
                print(f"Download {blob.name} from GCS!")
                blob.download_to_filename(destination_file)


gcs = GCStorage()

# ==========================================
# DATA LOADING FUNCTIONS
# ==========================================

@st.cache_data(show_spinner=False, ttl=3600)
def get_schedule(year):
    """Race schedule from FastF1."""
    try:
        schedule = fastf1.get_event_schedule(year)
        return schedule[schedule['RoundNumber'] > 0]
    except Exception:
        return pd.DataFrame()

def get_blob(year, round_num, session_type):
    schedule = get_schedule(year)
    schedule = schedule[schedule["RoundNumber"] == round_num]
    
    if session_type == "FP1":
        sub_event = str(list(schedule["Session1Date"])[0]).split(" ")[0] + "_" + list(schedule["Session1"])[0].replace(" ", "_")

    if session_type == "FP2":
        sub_event = str(list(schedule["Session2Date"])[0]).split(" ")[0] + "_" + list(schedule["Session2"])[0].replace(" ", "_")

    if session_type == "FP3":
        sub_event = str(list(schedule["Session3Date"])[0]).split(" ")[0] + "_" + list(schedule["Session3"])[0].replace(" ", "_")

    if session_type == "Q":
        sub_event = str(list(schedule["Session4Date"])[0]).split(" ")[0] + "_" + list(schedule["Session4"])[0].replace(" ", "_")
    
    if session_type == "R":
        sub_event = str(list(schedule["Session5Date"])[0]).split(" ")[0] + "_" + list(schedule["Session5"])[0].replace(" ", "_")

    event_date = str(list(schedule["EventDate"])[0]).split(" ")[0]
    event_name = str(list(schedule["EventName"])[0]).replace(" ", "_")
    blob = f"{year}/{event_date}_{event_name}/{sub_event}"
    return blob

def _has_local_cache(blob_prefix):
    """Check if local cache directory exists and has files."""
    blob_dir = os.path.join(CACHE_DIR, blob_prefix)
    return os.path.isdir(blob_dir) and len(os.listdir(blob_dir)) > 0


def _pull_gcs_to_local(blob_prefix):
    """Try to pull from GCS cache bucket to local cache. Returns True on success."""
    if not gcs.available:
        return False
    try:
        found = False
        for _ in gcs.list_blobs(GCS_CACHE_BUCKET, prefix=blob_prefix):
            found = True
            break
        if found:
            gcs.download_blob(GCS_CACHE_BUCKET, blob_prefix)
            return True
    except Exception as e:
        logger.warning("GCS cache read failed (disabling GCS): %s", e)
        gcs._disabled = True
    return False


def _push_local_to_gcs(blob_prefix):
    """Push local cache files to GCS cache bucket."""
    if not gcs.available:
        return
    blob_dir = os.path.join(CACHE_DIR, blob_prefix)
    if not os.path.isdir(blob_dir):
        return
    try:
        for file in os.listdir(blob_dir):
            gcs.upload_file(
                GCS_CACHE_BUCKET,
                blob_prefix.replace("\\", "/") + "/" + file,
                os.path.join(blob_dir, file))
    except Exception as e:
        logger.warning("GCS cache upload failed (disabling GCS): %s", e)
        gcs._disabled = True


def load(year, round_num, session_type, telemetry, weather, messages):
    blob = get_blob(year, round_num, session_type)
    logger.info("load() year=%s round=%s type=%s blob=%s", year, round_num, session_type, blob)

    # 1. Local cache hit — FastF1 will use f1_cache/ automatically
    had_local = _has_local_cache(blob)
    logger.info("local_cache=%s gcs_available=%s", had_local, gcs.available)

    # 2. GCS cache — pull to local if no local cache
    pulled = False
    if not had_local:
        pulled = _pull_gcs_to_local(blob)
        logger.info("gcs_pull=%s", pulled)

    # 3. Load session (FastF1 uses local cache, or fetches from API)
    session = fastf1.get_session(year, round_num, session_type)
    logger.info("f1_api_support=%s", session.f1_api_support)
    session.load(laps=True, telemetry=telemetry, weather=weather, messages=messages)
    logger.info("load complete: has_laps=%s has_results=%s",
                hasattr(session, '_laps'), hasattr(session, '_results'))

    # Ensure _laps exists even when f1_api_support is False (e.g. future sessions)
    if not hasattr(session, '_laps'):
        from fastf1.core import Laps
        session._laps = Laps(pd.DataFrame(), session=session)
        logger.warning("No lap data loaded — created empty _laps fallback")

    # Flag for downstream consumers to show user-facing warnings
    session._data_unavailable = session.laps.empty

    # 4. If we fetched fresh from API, push to GCS cache in background
    if not had_local and not pulled:
        threading.Thread(target=_push_local_to_gcs, args=(blob,), daemon=True).start()

    return session

@st.cache_data(show_spinner=False, ttl=3600)
def get_race_winner(year, round_num):
    """Winner string from FastF1."""
    try:
        session = load(
            year=year,
            round_num=round_num,
            session_type="R",
            telemetry=False,
            weather=False,
            messages=False
        )
        
        winner = session.results.iloc[0]
        return f"{winner['FullName']} ({winner['TeamName']})"
    except Exception:
        return "N/A"

@st.cache_resource(show_spinner=False)
def load_f1_session(year, round_num, session_type):
    """
    Loads complete F1 session data with telemetry information.
    Always uses FastF1 — telemetry cannot come from PostgreSQL.
    """
    try:
        return load(
            year=year,
            round_num=round_num,
            session_type=session_type,
            telemetry=True,
            weather=False,
            messages=True)
    except Exception as e:
        st.error(f"Error loading session data: {e}")
        return None

@st.cache_data(show_spinner=False, ttl=3600)
def get_event_highlights(year, round_num):
    """Event highlights from FastF1."""
    highlights = {
        "winner": "N/A",
        "pole": "N/A",
        "fastest_lap_driver": "N/A",
        "fastest_lap_time": ""
    }

    try:
        race = load(
            year=year,
            round_num=round_num,
            session_type="R",
            telemetry=False, 
            weather=False, 
            messages=False
        )

        
        if not race.results.empty:
            highlights["winner"] = race.results.iloc[0]['FullName']
            
            fastest_lap = race.laps.pick_fastest()
            
            if not pd.isnull(fastest_lap['LapTime']):
                driver_abbr = fastest_lap['Driver']
                driver_row = race.results[race.results['Abbreviation'] == driver_abbr]
                driver_full_name = driver_row.iloc[0]['FullName'] if not driver_row.empty else driver_abbr
                
                ts = fastest_lap['LapTime'].total_seconds()
                m = int(ts // 60)
                s = ts % 60
                
                highlights["fastest_lap_driver"] = driver_full_name 
                highlights["fastest_lap_time"] = f"{m:02d}:{s:06.3f}"

        qualy = load(
            year=year,
            round_num=round_num,
            session_type="Q",
            telemetry=False, 
            weather=False, 
            messages=False
        )

        if not qualy.results.empty:
            highlights["pole"] = qualy.results.iloc[0]['FullName']
            
    except Exception:
        pass 
    
    return highlights