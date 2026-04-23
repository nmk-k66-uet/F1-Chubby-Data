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

from google.cloud import storage

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


class GCStorage:
    def __init__(self):
        self.client = storage.Client()

    def get_bucket(self, bucket_name):
        return self.client.get_bucket(bucket_name)

    def upload_file(self, bucket_name, blob_destination, file_path):
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
    try:
        found = False
        for _ in gcs.list_blobs(GCS_CACHE_BUCKET, prefix=blob_prefix):
            found = True
            break
        if found:
            gcs.download_blob(GCS_CACHE_BUCKET, blob_prefix)
            return True
    except Exception as e:
        logger.warning("GCS cache read failed: %s", e)
    return False


def _push_local_to_gcs(blob_prefix):
    """Push local cache files to GCS cache bucket."""
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
        logger.warning("GCS cache upload failed: %s", e)


def load(year, round_num, session_type, telemetry, weather, messages):
    blob = get_blob(year, round_num, session_type)

    # 1. Local cache hit — FastF1 will use f1_cache/ automatically
    had_local = _has_local_cache(blob)

    # 2. GCS cache — pull to local if no local cache
    if not had_local:
        _pull_gcs_to_local(blob)

    # 3. Load session (FastF1 uses local cache, or fetches from API)
    session = fastf1.get_session(year, round_num, session_type)
    session.load(telemetry=telemetry, weather=weather, messages=messages)

    # 4. If we fetched fresh from API, push to GCS cache for next time
    if not had_local:
        _push_local_to_gcs(blob)

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