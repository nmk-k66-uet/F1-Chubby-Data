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
from core import db

# ==========================================
# CACHE CONFIGURATION
# ==========================================
CACHE_DIR = 'f1_cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Enable FastF1 caching and suppress verbose logging
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

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
        session = fastf1.get_session(year, round_num, 'R')
        session.load(telemetry=False, weather=False, messages=False)
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
        session = fastf1.get_session(year, round_num, session_type)
        session.load(telemetry=True, weather=False)
        return session
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
        race = fastf1.get_session(year, round_num, 'R')
        race.load(telemetry=False, weather=False, messages=False)
        
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

        qualy = fastf1.get_session(year, round_num, 'Q')
        qualy.load(telemetry=False, weather=False, messages=False)
        if not qualy.results.empty:
            highlights["pole"] = qualy.results.iloc[0]['FullName']
            
    except Exception:
        pass 
    
    return highlights