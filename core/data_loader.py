"""
Data Loader Module - FastF1 Session and Event Data Retrieval

This module provides cached functions to fetch F1 data from FastF1 library:
- Race schedule for a given year
- Race winners and results
- Qualifying and race session data with telemetry
- Event highlights (winner, pole position, fastest lap)

All functions use Streamlit's @st.cache_data decorator for performance optimization.
Data is cached locally in the 'f1_cache' directory.
"""

import streamlit as st
import fastf1
import pandas as pd
import os

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

@st.cache_data(show_spinner=False)
def get_schedule(year):
    """
    Retrieves the F1 race schedule for a given year.
    
    Args:
        year (int): The F1 season year (e.g., 2024, 2025).
    
    Returns:
        pd.DataFrame: Schedule dataframe containing RoundNumber, EventName, EventDate, Country, etc.
                     Filters out placeholder rounds (RoundNumber <= 0).
                     Returns empty DataFrame if schedule unavailable.
    
    Caching: Results are cached by Streamlit for the session duration.
    """
    try:
        schedule = fastf1.get_event_schedule(year)
        return schedule[schedule['RoundNumber'] > 0]
    except:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def get_race_winner(year, round_num):
    """
    Retrieves the winner of a specific race.
    
    Args:
        year (int): The F1 season year.
        round_num (int): The round number of the race (1-24).
    
    Returns:
        str: Winner's full name and team name formatted as "Name (TeamName)".
             Returns "N/A" if data unavailable.
    
    Output: Fetches race ('R') session results from FastF1.
    Caching: Results cached for performance.
    """
    try:
        session = fastf1.get_session(year, round_num, 'R')
        session.load(telemetry=False, weather=False, messages=False)
        winner = session.results.iloc[0]
        # Format: "Full Name (Team Name)"
        return f"{winner['FullName']} ({winner['TeamName']})"
    except:
        return "N/A"

@st.cache_data(show_spinner=False)
def load_f1_session(year, round_num, session_type):
    """
    Loads complete F1 session data with telemetry information.
    
    Args:
        year (int): The F1 season year.
        round_num (int): The round number (1-24).
        session_type (str): Type of session - 'FP1', 'FP2', 'FP3', 'Q' (Qualifying), 'S' (Sprint), 'R' (Race).
    
    Returns:
        fastf1.Session: Session object with driver data, lap times, and telemetry information.
                       Returns None if session fails to load.
    
    Output: Includes telemetry data but excludes weather and radio messages for performance.
    Caching: Session data cached for the session duration.
    """
    try:
        session = fastf1.get_session(year, round_num, session_type)
        session.load(telemetry=True, weather=False)
        return session
    except Exception as e:
        st.error(f"Error loading session data: {e}")
        return None

@st.cache_data(show_spinner=False)
def get_event_highlights(year, round_num):
    """
    Retrieves key highlights for a race event: winner, pole position, and fastest lap.
    
    Args:
        year (int): The F1 season year.
        round_num (int): The round number (1-24).
    
    Returns:
        dict: Dictionary with keys:
            - 'winner': Race winner's full name (str)
            - 'pole': Pole position driver's full name (str)
            - 'fastest_lap_driver': Driver who set fastest lap (str)
            - 'fastest_lap_time': Fastest lap time formatted as "MM:SS.sss" (str)
              All values default to "N/A" or empty string if unavailable.
    
    Process:
        1. Load race session to extract winner and fastest lap
        2. Load qualifying session to extract pole position
        3. Format lap time from timedelta to readable format
    
    Caching: Results cached for performance.
    """
    highlights = {
        "winner": "N/A",                    # Race winner
        "pole": "N/A",                      # Pole position driver
        "fastest_lap_driver": "N/A",        # Fastest lap driver
        "fastest_lap_time": ""              # Fastest lap time (MM:SS.sss)
    }
    
    try:
        # === GET RACE WINNER & FASTEST LAP ===
        race = fastf1.get_session(year, round_num, 'R')
        race.load(telemetry=False, weather=False, messages=False)
        
        if not race.results.empty:
            # Get race winner (first position finisher)
            highlights["winner"] = race.results.iloc[0]['FullName']
            
            # Get fastest lap info
            fastest_lap = race.laps.pick_fastest()
            
            if not pd.isnull(fastest_lap['LapTime']):
                # Get driver who set fastest lap
                driver_abbr = fastest_lap['Driver']
                driver_row = race.results[race.results['Abbreviation'] == driver_abbr]
                driver_full_name = driver_row.iloc[0]['FullName'] if not driver_row.empty else driver_abbr
                
                # Convert timedelta to MM:SS.sss format
                ts = fastest_lap['LapTime'].total_seconds()
                m = int(ts // 60)
                s = ts % 60
                
                highlights["fastest_lap_driver"] = driver_full_name 
                highlights["fastest_lap_time"] = f"{m:02d}:{s:06.3f}"

        # === GET POLE POSITION ===
        qualy = fastf1.get_session(year, round_num, 'Q')
        qualy.load(telemetry=False, weather=False, messages=False)
        if not qualy.results.empty:
            # Pole position is the driver with fastest qualifying time
            highlights["pole"] = qualy.results.iloc[0]['FullName']
            
    except Exception:
        # If any error occurs, return defaults
        pass 
    
    return highlights