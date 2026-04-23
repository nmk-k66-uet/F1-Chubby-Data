"""
Data Loader Module - F1 Session and Event Data Retrieval

Data sources (in priority order):
  1. Cloud SQL PostgreSQL (calendar, results, standings)
  2. FastF1 library fallback (when PG unavailable or LOCAL_MODE)

FastF1 is ALWAYS used for full session objects (telemetry, laps) — those stay unchanged.
"""

import streamlit as st
import fastf1
import pandas as pd
import os
import shutil

from core import db

from google.cloud import storage
# ==========================================
# CACHE CONFIGURATION
# ==========================================
BUCKET = "f1chubby-raw-gen-lang-client-0314607994"
CACHE_DIR = 'f1_cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Enable FastF1 caching and suppress verbose logging
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

STORAGE_CLASSES = ('STANDARD', 'NEARLINE', 'COLDLINE', 'ARCHIVE')

class GCStorage:
    def __init__(self, key_path=None):
        if key_path and os.path.exists(key_path):
            self.client = storage.Client.from_service_account_json(key_path)
        else:
            self.client = storage.Client()

    def create_bucket(self, bucket_name, storage_class, bucket_location='US'):
        bucket = self.client.bucket(bucket_name)
        bucket.storage_class = storage_class
        self.client.create_bucket(bucket, bucket_location)        

    def get_bucket(self, bucket_name):
        return self.client.get_bucket(bucket_name)

    def list_buckets(self):
        buckets = self.client.list_buckets()
        return [bucket.name for bucket in buckets]

    def upload_file(self, bucket_name, blob_destination, file_path):
        print(f"Upload {file_path} to GCS!")
        content_type = "application/octet-stream"
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_destination)
        blob.upload_from_filename(file_path, content_type=content_type)
        return blob

    def list_blobs(self, bucket_name):
        return self.client.list_blobs(bucket_name)
    
    def check_blob_exists(self, bucket_name, blob_name):
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()

    def download_blob(self, bucket_name, source_blob_name):
        """Downloads a blob from the bucket."""
        blobs = self.list_blobs(bucket_name)
        blob_path = os.path.join(CACHE_DIR, source_blob_name)
        os.makedirs(blob_path, exist_ok=True)

        for blob in blobs:
            if source_blob_name in blob.name:
                print(f"Download {blob.name} from GCS!")
                blob.download_to_filename(os.path.join(CACHE_DIR, blob.name))


key_path = "gcs-key/gen-lang-client-0314607994-ff9d436a97ef.json"
gcs = GCStorage(key_path=key_path)

# ==========================================
# DATA LOADING FUNCTIONS
# ==========================================

@st.cache_data(show_spinner=False, ttl=3600)
def get_schedule(year):
    """Race schedule from PostgreSQL, fallback to FastF1."""
    rows = db.query(
        "SELECT round AS \"RoundNumber\", event_name AS \"EventName\", "
        "event_date AS \"EventDate\", country AS \"Country\", "
        "circuit AS \"Location\", event_format AS \"EventFormat\" "
        "FROM race_calendar WHERE year=%s ORDER BY round",
        (year,),
    )
    if rows:
        df = pd.DataFrame(rows)
        df["EventDate"] = pd.to_datetime(df["EventDate"])
        return df

    # Fallback: FastF1
    try:
        schedule = fastf1.get_event_schedule(year)
        return schedule[schedule['RoundNumber'] > 0]
    except:
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

    blob = f"{year}/{str(list(schedule['EventDate'])[0]).split(' ')[0]}_{str(list(schedule['EventName'])[0]).replace(' ', '_')}/{sub_event}"
    return blob

def load(year, round_num, session_type, telemetry, weather, messages):
    blob = get_blob(year, round_num, session_type)
    is_exist = False
    for sub_blob in gcs.list_blobs(BUCKET):
        if blob in sub_blob.name:
            is_exist = True
            break
    if is_exist:
        gcs.download_blob(BUCKET, blob)

    session = fastf1.get_session(year, round_num, session_type)
    session.load(telemetry=telemetry, weather=weather, messages=messages)

    if not is_exist:
        for file in os.listdir(os.path.join(CACHE_DIR, blob)):
            gcs.upload_file(
                BUCKET, 
                blob.replace("\\", "/") + "/" + file, 
                os.path.join(CACHE_DIR, blob, file))

    shutil.rmtree(os.path.join(CACHE_DIR, str(year)))

    return session

@st.cache_data(show_spinner=False, ttl=3600)
def get_race_winner(year, round_num):
    """Winner string from PostgreSQL, fallback to FastF1."""
    rows = db.query(
        "SELECT full_name, team_name FROM session_results "
        "WHERE year=%s AND round=%s AND session_type='R' AND position=1",
        (year, round_num),
    )
    if rows:
        r = rows[0]
        return f"{r['full_name']} ({r['team_name']})"

    # Fallback: FastF1
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
    except:
        return "N/A"

@st.cache_data(show_spinner=False)
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
    """Event highlights from PostgreSQL, fallback to FastF1."""
    highlights = {
        "winner": "N/A",
        "pole": "N/A",
        "fastest_lap_driver": "N/A",
        "fastest_lap_time": ""
    }

    # Try PostgreSQL first
    rows = db.query(
        "SELECT full_name, team_name, position, session_type, best_lap_ms "
        "FROM session_results "
        "WHERE year=%s AND round=%s AND session_type IN ('R','Q') "
        "ORDER BY session_type, position",
        (year, round_num),
    )
    if rows:
        for r in rows:
            if r["session_type"] == "R" and r["position"] == 1:
                highlights["winner"] = r["full_name"]
            if r["session_type"] == "Q" and r["position"] == 1:
                highlights["pole"] = r["full_name"]
        # Fastest lap: smallest best_lap_ms among race finishers
        race_rows = [r for r in rows if r["session_type"] == "R" and r.get("best_lap_ms")]
        if race_rows:
            best = min(race_rows, key=lambda x: x["best_lap_ms"])
            ts = best["best_lap_ms"] / 1000.0
            m = int(ts // 60)
            s = ts % 60
            highlights["fastest_lap_driver"] = best["full_name"]
            highlights["fastest_lap_time"] = f"{m:02d}:{s:06.3f}"
            return highlights

        # PG had rows but no best_lap_ms — try FastF1 laps for fastest lap only
        try:
            race = fastf1.get_session(year, round_num, 'R')
            race.load(telemetry=False, weather=False, messages=False)
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
        except Exception:
            pass
        return highlights

    # Fallback: FastF1
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
            # Pole position is the driver with fastest qualifying time
            highlights["pole"] = qualy.results.iloc[0]['FullName']
            

            
    except Exception:
        pass 
    
    return highlights