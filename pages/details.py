"""Details Page - Comprehensive Race Weekend Analysis

In-depth race-by-race analysis dashboard:
- Pre-race predictions and tactical analysis
- Live race updates with probability tracking
- Race strategy and tire management
- Lap-by-lap timing and position analysis
- Driver telemetry comparison (speed, throttle, brake, RPM)
- Track dominance visualization
- Race control messages and events timeline
- Interactive replay visualization

"""

import streamlit as st
import pandas as pd
import fastf1
from core.config import get_flag_url
from core.data_loader import get_event_highlights, load_f1_session
from components.tab_results import fragment_results, fragment_practice_results, get_practice_results_df
from components.tab_positions import fragment_positions
from components.tab_strategy import fragment_strategy, fragment_practice_strategy
from components.tab_lap_times import fragment_lap_times
from components.tab_track_dominance import fragment_dominance
from components.tab_telemetry import render_telemetry_tab
from components.predictor_ui import render_predictor_tab
from components.replay_engine import fragment_replay_continuous
from components.tab_race_control import fragment_race_control
from components.tab_live_race import fragment_live_race
from components.navbar import render_navbar

def render():
    """Render the comprehensive race weekend analysis dashboard.
    
    Output: Displays multiple tabs for complete race analysis:
    - Predictions: Pre-race podium probabilities and AI tactical analysis
    - Results: Qualifying and race results with positions and times
    - Lap Times: Lap-by-lap timing with dynamic driver selection
    - Telemetry: 6 telemetry charts (speed, gear, throttle, brake, RPM, DRS)
    - Positions: Lap-by-lap position changes and gained/lost analysis
    - Strategy: Tire strategy timeline and stint performance metrics
    - Track Dominance: Head-to-head driver comparison on track
    - Race Control: Timeline of all official race events and flags
    - Live Race: Real-time race probabilities and momentum tracking
    - Replay: Interactive race visualization with car positions
    """
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
        </style>
    """, unsafe_allow_html=True)
    
    if not st.session_state.get('selected_event'):
        st.warning("Please select a race from the Calendar first.")
        if st.button("Return to Calendar"):
            st.switch_page("pages/race_analytics.py")
        return

    event_info = st.session_state['selected_event']
    year, round_num, event_name = event_info['year'], event_info['round'], event_info['name']
    flag_url = get_flag_url(event_info['country'])

    col_back, col_title, col_session = st.columns([0.15, 3.5, 1.2], vertical_alignment="center")

    with col_back:
        if st.button("←", key="back_home_btn"):
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith(('ch_', 'sel_', 'del_', 'tel_', 'dom_')) or k in ['lt_boxes', 'lt_box_counter', 'sel_all_pos', 'replay_session_id', 'js_payload', 'predictions_race_id', 'predictions_df', 'gemini_insight', 'setup_profiler_fig']]
            for key in keys_to_clear: del st.session_state[key]
            st.switch_page("pages/home.py")

    with col_title:
        st.markdown(f"<h2 style='margin: 0;'><img src='{flag_url}' width='48' style='border-radius:6px; vertical-align:middle; margin-right:15px; box-shadow: 0 0 4px rgba(255,255,255,0.3);'> {event_name} {year}</h2>", unsafe_allow_html=True)
    
    with col_session:
        schedule = fastf1.get_event_schedule(year)
        event_row = schedule[schedule['RoundNumber'] == round_num].iloc[0]
        format_type = event_row.get('EventFormat', 'conventional').lower()
        
        if format_type == 'sprint':
            available_sessions = ["FP1", "Sprint", "Sprint Shootout", "Qualifying", "Race"]
            session_map = {"FP1": "FP1", "Sprint": "S", "Sprint Shootout": "SS", "Qualifying": "Q", "Race": "R"}
        elif format_type == 'sprint_qualifying': 
            available_sessions = ["FP1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"]
            session_map = {"FP1": "FP1", "Sprint Qualifying": "SQ", "Sprint": "S", "Qualifying": "Q", "Race": "R"}
        else:
            available_sessions = ["FP1", "FP2", "FP3", "Qualifying", "Race"]
            session_map = {"FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "Qualifying": "Q", "Race": "R"}

        selected_session_name = st.selectbox("Select Session:", available_sessions, index=len(available_sessions)-1, label_visibility="collapsed")
        session_code = session_map[selected_session_name]

    with st.spinner(f"Loading session details for {selected_session_name}..."):
        session = load_f1_session(year, round_num, session_code)

    if session is None:
        st.warning("Unable to load data for this session.")
        return

    if getattr(session, '_data_unavailable', False):
        st.warning("⚠️ Detailed timing data (laps, telemetry) is not yet available for this session. "
                   "Only basic results are shown. Data usually appears a few hours after the session ends.")

    drivers = session.results['Abbreviation'].dropna().unique().tolist()

    st.markdown("""
        <style>
            .stTabs [data-baseweb="tab-list"] {
                display: flex;
                width: 100%;
            }
            .stTabs [data-baseweb="tab"] {
                flex-grow: 1;
                justify-content: center;
                white-space: nowrap;
                padding-left: 0px;
                padding-right: 0px;
            }
        </style>
    """, unsafe_allow_html=True)

    if session_code.startswith('FP'):
        st.subheader(f"Session Highlights - {selected_session_name}")
        practice_df = get_practice_results_df(session)
        practice_top3 = practice_df.head(3)
        
        col_p1, col_p2, col_p3 = st.columns(3)
        p_cols = [col_p1, col_p2, col_p3]
        
        for i, (_, row) in enumerate(practice_top3.iterrows()):
            if i >= 3: break
            with p_cols[i]:
                with st.container(border=True):
                    time_str = row['Fastest Lap']
                    driver_name = row['Driver']
                    
                    st.markdown(f"""
                        <div style='display: flex; justify-content: space-between;'>
                            <div>
                                <div style='color: #888; font-size: 0.85rem; font-weight: bold;'>P{i+1}</div>
                                <div style='font-size: 1.4rem; font-weight: bold;'>{driver_name}</div>
                                <div style='font-family: monospace; color: #00cc66;'>{time_str}</div>
                            </div>
                            <div style='font-size: 2rem;'>{['🥇', '🥈', '🥉'][i]}</div>
                        </div>
                    """, unsafe_allow_html=True)
    else:
        highlights = get_event_highlights(year, round_num)
        col_win, col_pole, col_fast = st.columns(3)
        
        with col_win:
            with st.container(border=True):
                st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: flex-start;'><div><div style='color: #888; font-size: 0.85rem; font-weight: bold; letter-spacing: 1px;'>RACE WINNER</div><div style='font-size: 1.6rem; font-weight: bold; margin-top: 5px;'>{highlights['winner']}</div><div style='font-size: 1.1rem; margin-top: 2px; visibility: hidden;'>&nbsp;</div></div><div style='font-size: 2.2rem; opacity: 0.9;'>🏆</div></div>", unsafe_allow_html=True)
        with col_pole:
            with st.container(border=True):
                st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: flex-start;'><div><div style='color: #888; font-size: 0.85rem; font-weight: bold; letter-spacing: 1px;'>POLE POSITION</div><div style='font-size: 1.6rem; font-weight: bold; margin-top: 5px;'>{highlights['pole']}</div><div style='font-size: 1.1rem; margin-top: 2px; visibility: hidden;'>&nbsp;</div></div><div style='font-size: 2.2rem; opacity: 0.9;'>⏱️</div></div>", unsafe_allow_html=True)
        with col_fast:
            with st.container(border=True):
                time_html = f"<div style='font-size: 1.1rem; color: white; margin-top: 2px; font-family: monospace;'>{highlights['fastest_lap_time']}</div>" if highlights['fastest_lap_time'] else "<div style='font-size: 1.1rem; margin-top: 2px; visibility: hidden;'>&nbsp;</div>"
                st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: flex-start;'><div><div style='color: #888; font-size: 0.85rem; font-weight: bold; letter-spacing: 1px;'>FASTEST LAP</div><div style='font-size: 1.6rem; font-weight: bold; margin-top: 5px;'>{highlights['fastest_lap_driver']}</div>{time_html}</div><div style='font-size: 2.2rem; opacity: 0.9;'>🚀</div></div>", unsafe_allow_html=True)

    st.divider()

    if session_code.startswith('FP'):
        tab_res, tab_strat, tab_laps, tab_dom, tab_rc, tab_tel = st.tabs([
            "Results", "Strategy", "Lap Times", 
            "Track Dominance", "Race Control", "Telemetry"
        ])
        
        with tab_res:
            fragment_practice_results(session, selected_session_name)
        with tab_strat:
            fragment_practice_strategy(session)
        with tab_laps: 
            fragment_lap_times(session, drivers)
        with tab_dom: 
            fragment_dominance(session, drivers)
        with tab_rc:
            fragment_race_control(session)
        with tab_tel:
            render_telemetry_tab(session, drivers)

    else:
        # RACE / QUALIFYING / SPRINT
        tab_res, tab_pos, tab_strat, tab_laps, tab_dom, tab_tel, tab_predict, tab_replay, tab_live = st.tabs([
            "Results", "Positions", "Strategy", "Lap Times", 
            "Track Dominance", "Telemetry", "Race Predictor", "Replay", "Live Timing"
        ])
        
        with tab_res:
            fragment_results(session, session_code, selected_session_name)
        with tab_pos:
            fragment_positions(session, drivers, selected_session_name)
        with tab_strat:
            fragment_strategy(session)
        with tab_laps:
            fragment_lap_times(session, drivers)
        with tab_dom:
            fragment_dominance(session, drivers)
        with tab_tel:
            render_telemetry_tab(session, drivers)
        with tab_predict:
            render_predictor_tab(session, year, round_num, event_name)
        with tab_replay:
            fragment_replay_continuous(session, year, round_num, session_code)
        with tab_live:
            fragment_live_race(session)

render()