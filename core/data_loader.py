import streamlit as st
import fastf1
import pandas as pd
import os

# --- Thiết lập Cache cho FastF1 ---
CACHE_DIR = 'f1_cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

# --- Các hàm Tải Dữ liệu ---
@st.cache_data(show_spinner=False)
def get_schedule(year):
    try:
        schedule = fastf1.get_event_schedule(year)
        return schedule[schedule['RoundNumber'] > 0]
    except:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def get_race_winner(year, round_num):
    try:
        session = fastf1.get_session(year, round_num, 'R')
        session.load(telemetry=False, weather=False, messages=False)
        winner = session.results.iloc[0]
        # Đổi Abbreviation thành FullName
        return f"{winner['FullName']} ({winner['TeamName']})"
    except:
        return "N/A"

@st.cache_data(show_spinner=False)
def load_f1_session(year, round_num, session_type):
    try:
        session = fastf1.get_session(year, round_num, session_type)
        session.load(telemetry=True, weather=False)
        return session
    except Exception as e:
        st.error(f"Error loading session data: {e}")
        return None

@st.cache_data(show_spinner=False)
def get_event_highlights(year, round_num):
    highlights = {"winner": "N/A", "pole": "N/A", "fastest_lap_driver": "N/A", "fastest_lap_time": ""}
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