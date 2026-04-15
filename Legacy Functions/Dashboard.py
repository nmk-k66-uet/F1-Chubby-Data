import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
from datetime import datetime
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import time
import os
import json
from google import genai
import streamlit.components.v1 as components 

# IMPORT LÕI MACHINE LEARNING
import core.ml_core as ml_core

# --- PAGE CONFIG ---
st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    [data-testid="column"] > div {
        overflow: visible !important;
    }
    div[data-baseweb="popover"] > div {
        max-height: 300px !important;
        overflow-y: auto !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    [data-testid="stSidebar"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# FastF1 Cache Setup
CACHE_DIR = 'f1_cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.plotting.setup_mpl(mpl_timedelta_support=False)
fastf1.set_log_level('ERROR')

# Initialize Session State
if 'selected_event' not in st.session_state:
    st.session_state['selected_event'] = None
if 'selected_year' not in st.session_state:
    st.session_state['selected_year'] = 2026

# --- COUNTRY CODES ---
COUNTRY_CODES = {
    "Bahrain": "bh", "Saudi Arabia": "sa", "Australia": "au", "Japan": "jp", 
    "China": "cn", "USA": "us", "United States": "us", "Miami": "us", 
    "Italy": "it", "Monaco": "mc", "Spain": "es", "Canada": "ca", 
    "Austria": "at", "UK": "gb", "United Kingdom": "gb", "Hungary": "hu", 
    "Belgium": "be", "Netherlands": "nl", "Singapore": "sg", 
    "Azerbaijan": "az", "Mexico": "mx", "Brazil": "br", "Las Vegas": "us", 
    "Qatar": "qa", "Abu Dhabi": "ae", "United Arab Emirates": "ae"
}

def get_flag_url(country_name):
    code = COUNTRY_CODES.get(country_name, "un")
    return f"https://flagcdn.com/h40/{code}.png"

# --- DATA LOADING FUNCTIONS ---
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
        return f"{winner['Abbreviation']} ({winner['TeamName']})"
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

# ==========================================
# TAB FRAGMENTS 
# ==========================================

@st.fragment
def fragment_positions(session, drivers, session_name):
    sub_chart, sub_rc, sub_analysis = st.tabs(["📈 Position Chart", "🚨 Race Control", "📊 Analysis"])
    with sub_chart:
        col_title, col_filter = st.columns([3, 1])
        with col_title:
            st.subheader(f"Lap-by-Lap Position Changes - {session_name}")
            st.caption("Note: Within a team, the second driver is shown with a dashed line.")
        with col_filter:
            with st.expander("Filter Drivers", expanded=False):
                for drv in drivers:
                    if f"ch_{drv}" not in st.session_state: st.session_state[f"ch_{drv}"] = True
                def toggle_all():
                    master_val = st.session_state["sel_all_pos"]
                    for d in drivers: st.session_state[f"ch_{d}"] = master_val
                st.checkbox("Select All", value=True, key="sel_all_pos", on_change=toggle_all)
                selected_drivers = [drv for drv in drivers if st.checkbox(drv, key=f"ch_{drv}")]

        if not selected_drivers: st.warning("Please select at least one driver to view data.")
        else:
            fig_pos = go.Figure()
            all_laps = session.laps
            team_count = {}
            for drv in selected_drivers:
                drv_laps = all_laps.pick_drivers(drv).dropna(subset=['Position'])
                if not drv_laps.empty:
                    driver_info = session.get_driver(drv)
                    team_name = driver_info['TeamName']
                    color = f"#{driver_info['TeamColor']}"
                    if color == "#nan" or not color: color = "white"
                    line_style = 'solid' if team_name not in team_count else 'dash'
                    team_count[team_name] = 1
                    fig_pos.add_trace(go.Scatter(x=drv_laps['LapNumber'], y=drv_laps['Position'], mode='lines', name=drv, line=dict(color=color, width=2.5, dash=line_style), hovertemplate=f"<b>{drv}</b> ({team_name})<br>Lap: %{{x}}<br>Pos: P%{{y}}<extra></extra>"))

            max_lap = int(all_laps['LapNumber'].max()) if not all_laps.empty else 50
            fig_pos.update_layout(yaxis=dict(autorange="reversed", tickmode='linear', dtick=1), xaxis=dict(title="Lap", range=[1, max_lap], tickmode='linear', tick0=1, dtick=5, showgrid=True, gridcolor="rgba(255,255,255,0.1)"), hovermode="x unified", height=550, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=40, b=80), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
            st.plotly_chart(fig_pos, width='stretch')

    with sub_rc:
        st.subheader("FIA Race Control Timeline")
        rcm_df = session.race_control_messages
        if not rcm_df.empty:
            rcm_display = rcm_df[['Time', 'Category', 'Flag', 'Message']].copy()
            rcm_display['Time'] = rcm_display['Time'].apply(lambda ts: ts.strftime("%H:%M:%S") if pd.notna(ts) else "")
            st.dataframe(rcm_display, width='stretch', hide_index=True)
        else:
            st.info("No race control messages for this session.")

    with sub_analysis:
        st.subheader("Places Gained/Lost Summary")
        analysis_data = []
        for _, row in session.results.iterrows():
            pos, grid = pd.to_numeric(row['Position'], errors='coerce'), pd.to_numeric(row['GridPosition'], errors='coerce')
            change = f"↑ +{int(grid-pos)}" if grid > pos else (f"↓ {int(grid-pos)}" if grid < pos else "- 0")
            if grid == 0: change = "Pit Start"
            analysis_data.append({'Final Pos': str(int(pos)) if pd.notna(pos) else "N/A", 'Driver': row['FullName'], 'Team': row['TeamName'], 'Grid': str(int(grid)) if grid > 0 else "Pit", 'Change': change, 'Status': row['Status']})
        def style_change(val): return 'color: #00cc66; font-weight: bold;' if '↑' in str(val) else ('color: #ff4b4b; font-weight: bold;' if '↓' in str(val) else 'color: gray;')
        st.dataframe(pd.DataFrame(analysis_data).style.map(style_change, subset=['Change']), width='stretch', hide_index=True)

@st.fragment
def fragment_lap_times(session, drivers):
    if 'lt_boxes' not in st.session_state: st.session_state['lt_boxes'] = ['box_0', 'box_1'] 
    if 'lt_box_counter' not in st.session_state: st.session_state['lt_box_counter'] = 2
    boxes = st.session_state['lt_boxes']
    n = len(boxes)
    c_title, c_add = st.columns([4, 1])
    with c_title: st.subheader("Lap Time Comparison")
    
    def add_driver():
        st.session_state['lt_boxes'].append(f"box_{st.session_state['lt_box_counter']}")
        st.session_state['lt_box_counter'] += 1
        
    with c_add:
        st.button("➕ Add Driver", disabled=n >= 6, width='stretch', on_click=add_driver)

    sel_drivers = []
    for i in range(0, n, 3):
        cols = st.columns(3)
        for j in range(3):
            idx = i + j
            if idx < n:
                b_id = boxes[idx]
                with cols[j]:
                    if n >= 3:
                        sc1, sc2 = st.columns([4, 1])
                        with sc1: drv = st.selectbox("Driver", drivers, index=idx%len(drivers), key=f"sel_{b_id}", label_visibility="collapsed")
                        with sc2: 
                            def remove_driver(box_id=b_id):
                                st.session_state['lt_boxes'].remove(box_id)
                            st.button("✖", key=f"del_{b_id}", on_click=remove_driver)
                    else: drv = st.selectbox("Driver", drivers, index=idx%len(drivers), key=f"sel_{b_id}", label_visibility="collapsed")
                    sel_drivers.append(drv)

    unique_drv = list(dict.fromkeys(sel_drivers))
    if unique_drv:
        fig_l = go.Figure()
        for drv in unique_drv:
            d_laps = session.laps.pick_drivers(drv).dropna(subset=['LapTime'])
            if not d_laps.empty:
                c = f"#{session.get_driver(drv)['TeamColor']}" if str(session.get_driver(drv)['TeamColor']) != 'nan' else 'white'
                fig_l.add_trace(go.Scatter(x=d_laps['LapNumber'], y=d_laps['LapTime'].dt.total_seconds(), mode='lines+markers', name=drv, line=dict(color=c, width=2, shape='spline')))
        fig_l.update_layout(xaxis_title="Lap", yaxis_title="Time (s)", hovermode="x unified", height=600)
        st.plotly_chart(fig_l, width='stretch')

@st.fragment
def fragment_dominance(session, drivers):
    col_title, col_ctrls = st.columns([1.2, 2.8])
    with col_title:
        st.subheader("Track Dominance & Speed Trace")
    with col_ctrls:
        c1, c2, c3, c4, c5 = st.columns([2, 2, 0.5, 2, 2])
        with c1: drv1 = st.selectbox("Driver 1", drivers, index=0, key="dom_d1")
        with c2:
            laps1 = session.laps.pick_drivers(drv1)['LapNumber'].dropna().astype(int).tolist()
            sel_lap1 = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps1], index=0, key="dom_l1")
        with c3: st.markdown("<div style='text-align: center; font-weight: bold; font-size: 1.2rem; margin-top: 35px;'>VS</div>", unsafe_allow_html=True)
        with c4: drv2 = st.selectbox("Driver 2", drivers, index=1 if len(drivers)>1 else 0, key="dom_d2")
        with c5:
            laps2 = session.laps.pick_drivers(drv2)['LapNumber'].dropna().astype(int).tolist()
            sel_lap2 = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps2], index=0, key="dom_l2")

    st.divider()
    try:
        def get_lap_data(drv, sel):
            drv_laps = session.laps.pick_drivers(drv)
            if sel == "Fastest": return drv_laps.pick_fastest()
            else: return drv_laps[drv_laps['LapNumber'] == int(sel.replace("Lap ", ""))].iloc[0]

        lap1 = get_lap_data(drv1, sel_lap1)
        lap2 = get_lap_data(drv2, sel_lap2)
        
        if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']): st.warning("Selected laps do not have valid telemetry data.")
        else:
            tel1 = lap1.get_telemetry()
            tel2 = lap2.get_telemetry()
            c1 = f"#{session.get_driver(drv1)['TeamColor']}" if str(session.get_driver(drv1)['TeamColor']) != 'nan' else 'white'
            c2 = f"#{session.get_driver(drv2)['TeamColor']}" if str(session.get_driver(drv2)['TeamColor']) != 'nan' else 'white'
            if c1 == c2: c2 = "#00FFFF" 
                
            num_sectors = 50
            max_dist = max(tel1['Distance'].max(), tel2['Distance'].max())
            sector_length = max_dist / num_sectors
            tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
            tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)
            sectors = pd.DataFrame({'S1': tel1.groupby('MiniSector')['Speed'].mean(), 'S2': tel2.groupby('MiniSector')['Speed'].mean()}).fillna(0)
            conditions = [abs(sectors['S1'] - sectors['S2']) <= 2.0, sectors['S1'] > sectors['S2']]
            sectors['Dominant'] = np.select(conditions, [0, 1], default=2)
            tel1['Dominant'] = tel1['MiniSector'].map(sectors['Dominant'])
            
            col_map, col_speed = st.columns(2)
            with col_map:
                fig_map = go.Figure()
                tel1['Block'] = (tel1['Dominant'] != tel1['Dominant'].shift(1)).cumsum()
                block_ids = tel1['Block'].unique()
                show_leg1, show_leg2, show_leg0 = True, True, True
                for i, b in enumerate(block_ids):
                    group = tel1[tel1['Block'] == b].copy()
                    if i < len(block_ids) - 1: group = pd.concat([group, tel1[tel1['Block'] == block_ids[i+1]].iloc[0:1]])
                    dom_val = group['Dominant'].iloc[0]
                    color, drv_name = ("#FFFF00", "Neutral") if dom_val == 0 else (c1, f"{drv1} Faster") if dom_val == 1 else (c2, f"{drv2} Faster")
                    show_leg = False
                    if dom_val == 1 and show_leg1: show_leg = True; show_leg1 = False
                    elif dom_val == 2 and show_leg2: show_leg = True; show_leg2 = False
                    elif dom_val == 0 and show_leg0: show_leg = True; show_leg0 = False
                    fig_map.add_trace(go.Scatter(x=group['X'], y=group['Y'], mode='lines', line=dict(color=color, width=8), name=drv_name, showlegend=show_leg, hoverinfo='skip'))
                fig_map.update_layout(title="Track Dominance Map", xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=40, b=60), legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
                st.plotly_chart(fig_map, width='stretch')
                
            with col_speed:
                fig_speed = go.Figure()
                fig_speed.add_trace(go.Scatter(x=tel1['Distance'], y=tel1['Speed'], mode='lines', name=f"{drv1} ({sel_lap1})", line=dict(color=c1, width=2)))
                fig_speed.add_trace(go.Scatter(x=tel2['Distance'], y=tel2['Speed'], mode='lines', name=f"{drv2} ({sel_lap2})", line=dict(color=c2, width=2)))
                fig_speed.update_layout(title="Speed Trace", xaxis_title="Distance (m)", yaxis_title="Speed (km/h)", hovermode="x unified", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=40, b=60), xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
                st.plotly_chart(fig_speed, width='stretch')

            st.divider()
            
            st.subheader("Additional Telemetry Comparison")
            
            metrics = [('Throttle (%)', 'Throttle'), ('Brake', 'Brake'), ('RPM', 'RPM'), ('DRS', 'DRS')]
            for i in range(0, 4, 2):
                cols = st.columns(2)
                for j in range(2):
                    metric_title, metric_col = metrics[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            fig_ind = go.Figure()
                            fig_ind.add_trace(go.Scatter(x=tel1['Distance'], y=tel1[metric_col], mode='lines', line=dict(color=c1, width=2), name=f"{drv1}"))
                            fig_ind.add_trace(go.Scatter(x=tel2['Distance'], y=tel2[metric_col], mode='lines', line=dict(color=c2, width=2), name=f"{drv2}"))
                            fig_ind.update_layout(title=dict(text=f"<b>{metric_title} Comparison</b>", font=dict(size=16), x=0.02, y=0.95), legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, font=dict(size=11), bgcolor="rgba(0,0,0,0)"), height=320, hovermode="x unified", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=45, b=60), xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text="Distance (m)"), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"))
                            st.plotly_chart(fig_ind, width='stretch', config={'displaylogo': False})
    except Exception as e: st.error(f"Error processing telemetry data: {e}")

@st.fragment
def fragment_telemetry_card(session, drivers, chart_info, idx):
    gear_colors = {1: '#00FFFF', 2: '#FF7F50', 3: '#008080', 4: '#FF0000', 5: '#FF1493', 6: '#0000CD', 7: '#ADFF2F', 8: '#FFD700'}
    with st.container(border=True):
        c_title, c_drv, c_lap = st.columns([2, 1, 1])
        with c_drv: drv_sel = st.selectbox("Drv", drivers, key=f"tel_drv_{idx}", label_visibility="collapsed")
        with c_lap:
            laps_list = session.laps.pick_drivers(drv_sel)['LapNumber'].dropna().astype(int).tolist()
            lap_sel = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps_list], key=f"tel_lap_{idx}", label_visibility="collapsed")

        lap_str_title = "Fastest Lap" if lap_sel == "Fastest" else lap_sel
        with c_title:
            st.markdown(f"<div style='font-weight:bold; font-size:1.1rem; padding-top:2px; line-height:1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{drv_sel}'s {lap_str_title}<br><span style='color:#00cc66; font-size:0.9rem; letter-spacing: 0.5px;'>{chart_info['title'].upper()}</span></div>", unsafe_allow_html=True)
        try:
            drv_laps = session.laps.pick_drivers(drv_sel)
            lap_data = drv_laps.pick_fastest() if lap_sel == "Fastest" else drv_laps[drv_laps['LapNumber'] == int(lap_sel.replace("Lap ", ""))].iloc[0]
            if pd.isna(lap_data['LapTime']): st.warning("No telemetry data available.")
            else:
                tel = lap_data.get_telemetry().copy()
                drv_color = f"#{session.get_driver(drv_sel)['TeamColor']}" if str(session.get_driver(drv_sel)['TeamColor']) != 'nan' else 'white'
                fig = go.Figure()
                if chart_info['type'] == 'map':
                    tel['nGear'] = pd.to_numeric(tel['nGear'], errors='coerce').fillna(0).astype(int)
                    for gear in range(1, 9): fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color=gear_colors.get(gear, '#FFFFFF')), name=f"Gear {gear}", showlegend=True))
                    tel['Block'] = (tel['nGear'] != tel['nGear'].shift(1)).cumsum()
                    block_ids = tel['Block'].unique()
                    for k, b in enumerate(block_ids):
                        group = tel[tel['Block'] == b].copy()
                        if k < len(block_ids) - 1: group = pd.concat([group, tel[tel['Block'] == block_ids[k+1]].iloc[0:1]], ignore_index=True)
                        gear = int(group['nGear'].iloc[0])
                        fig.add_trace(go.Scatter(x=group['X'], y=group['Y'], mode='lines', line=dict(color=gear_colors.get(gear, '#FFFFFF'), width=5), name=f"Gear {gear}", showlegend=False, hoverinfo='skip'))
                    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1), legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5, font=dict(size=11)))
                else:
                    fig.add_trace(go.Scatter(x=tel['Distance'], y=tel[chart_info['metric']], mode='lines', line=dict(color=drv_color, width=2.5), hovertemplate="Dist: %{x}m<br>Value: %{y}<extra></extra>"))
                    fig.update_layout(xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text="Distance (m)"), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text=chart_info['unit']), hovermode="x unified", showlegend=False)
                fig.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=15), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        except Exception as e: st.error(f"Error rendering chart: {str(e)}")


# ==========================================
# LAZY-LOADED REPLAY ENGINE (NATIVE JS)
# Tích hợp Track Zones (DRS, Straights, Start/Finish, Corners Vector)
# ==========================================
# ==========================================
# LAZY-LOADED REPLAY ENGINE (NATIVE JS)
# Tích hợp Track Zones (DRS, Straights, Start/Finish, Corners Vector)
# Đã fix lỗi UX Thanh tiến trình (Progress Bar)
# ==========================================
def generate_and_cache_replay_payload(session, max_lap_avail, cache_path):
    st.info("Extracting data... This usually takes 1-2 minutes. Please do not switch tabs.")
    progress_bar = st.progress(0.0)
    status_text = st.empty()
    
    payload = {
        "frames": [], "laps_info": {}, "messages": [], "colors": {}, "track_path": [], 
        "corners": [],
        "max_lap": max_lap_avail, "min_x": 0, "max_x": 1, "min_y": 0, "max_y": 1
    }
    
    drivers = session.results['Abbreviation'].dropna().unique().tolist()
    for drv in drivers:
        info = session.get_driver(drv)
        payload["colors"][drv] = f"#{info['TeamColor']}" if str(info['TeamColor']) != 'nan' else '#FFFFFF'
        
    try:
        status_text.text("Phase 1/4: Extracting Track Geometry...")
        
        # Lấy quỹ đạo đường đua
        ref_lap = session.laps.pick_fastest()
        ref_tel = ref_lap.get_telemetry()
        payload["track_path"] = ref_tel[['X', 'Y']].dropna().values.tolist()
        payload["min_x"], payload["max_x"] = float(ref_tel['X'].min()), float(ref_tel['X'].max())
        payload["min_y"], payload["max_y"] = float(ref_tel['Y'].min()), float(ref_tel['Y'].max())
        
        # Lấy vạch Finish (Luôn là điểm đầu của flying lap)
        payload["finish_line"] = [float(ref_tel['X'].iloc[0]), float(ref_tel['Y'].iloc[0])]
        
        # Lấy vạch Start (Vị trí Grid ở Lap 1)
        try:
            lap1 = session.laps[session.laps['LapNumber'] == 1].iloc[0]
            lap1_tel = lap1.get_telemetry()
            payload["start_line"] = [float(lap1_tel['X'].iloc[0]), float(lap1_tel['Y'].iloc[0])]
        except: pass

        # Tính toán Góc Cua (Corners Vector)
        circuit_info = session.get_circuit_info()
        corners_data = []
        if circuit_info is not None and hasattr(circuit_info, 'corners'):
            center_x = (payload["min_x"] + payload["max_x"]) / 2
            center_y = (payload["min_y"] + payload["max_y"]) / 2
            
            for _, row in circuit_info.corners.iterrows():
                cx = float(row['X']); cy = float(row['Y'])
                vx = cx - center_x; vy = cy - center_y
                mag = (vx**2 + vy**2)**0.5
                if mag == 0: mag = 1
                corners_data.append({
                    "x": cx, "y": cy, "nx": vx/mag, "ny": vy/mag, "number": str(row.get('Number', ''))
                })
        payload["corners"] = corners_data
        
    except Exception as e: 
        print(f"Error parsing track geometry: {e}")
        pass

    progress_bar.progress(0.1)
    
    rcm_df = session.race_control_messages
    if not rcm_df.empty:
        for _, row in rcm_df.iterrows():
            t_val = row.get('Time')
            if pd.isna(t_val): continue
            try:
                if hasattr(t_val, 'total_seconds'):
                    t_sec = t_val.total_seconds()
                    time_str = f"T+{int(t_sec//60):02d}:{int(t_sec%60):02d}"
                else:
                    if hasattr(session, 't0_date') and session.t0_date is not None:
                        t_val_no_tz = t_val.tz_localize(None) if t_val.tzinfo else t_val
                        t0_no_tz = session.t0_date.tz_localize(None) if session.t0_date.tzinfo else session.t0_date
                        t_sec = (t_val_no_tz - t0_no_tz).total_seconds()
                    else: t_sec = 0
                    time_str = t_val.strftime("%H:%M:%S")
                flag_str = str(row['Flag']) if 'Flag' in row and pd.notna(row['Flag']) else "INFO"
                payload["messages"].append({
                    "t_sec": float(t_sec), "time_str": time_str,
                    "flag": flag_str, "msg": str(row.get('Message', ''))
                })
            except Exception as e: pass
            
    for lap in range(1, max_lap_avail + 1):
        status_text.text(f"Phase 2/4: Extracting Live Timing (Lap {lap}/{max_lap_avail})...")
        current_prog = 0.1 + 0.4 * (lap / max_lap_avail)
        progress_bar.progress(current_prog)
        
        laps_data = session.laps[session.laps['LapNumber'] == lap]
        if laps_data.empty: continue
        timing_data = []
        leader_time = None
        sorted_laps = laps_data.dropna(subset=['Position']).sort_values('Position')
        if not sorted_laps.empty: leader_time = sorted_laps.iloc[0]['Time']
            
        for _, row in sorted_laps.iterrows():
            drv = row['Driver']
            pos = int(row['Position'])
            gap = "Leader"
            if pos > 1 and pd.notna(row['Time']) and pd.notna(leader_time):
                gap = f"+{(row['Time'] - leader_time).total_seconds():.3f}s"
            elif pd.isna(row['Time']): gap = "OUT"
            
            lt_str = "N/A"
            if pd.notna(row['LapTime']):
                lt_sec = row['LapTime'].total_seconds()
                lt_str = f"{int(lt_sec // 60)}:{lt_sec % 60:06.3f}"
            timing_data.append({"pos": pos, "drv": drv, "gap": gap, "last_lap": lt_str, "tyre": row.get('Compound', 'Unknown')})
        
        end_t = leader_time.total_seconds() if pd.notna(leader_time) else session.laps['Time'].max().total_seconds()
        payload["laps_info"][str(lap)] = {"timing": timing_data, "end_t_sec": float(end_t)}

    min_time = session.laps['LapStartTime'].dropna().min()
    max_time = session.laps['Time'].dropna().max()
    timestamps = pd.timedelta_range(start=min_time, end=max_time, freq='100ms')
    
    df_list = []
    for i, drv in enumerate(drivers):
        status_text.text(f"Phase 3/4: Interpolating car trajectories ({i+1}/{len(drivers)})...")
        current_prog = 0.5 + 0.4 * ((i + 1) / len(drivers))
        progress_bar.progress(current_prog)
        
        try:
            drv_laps = session.laps.pick_drivers(drv)
            if not drv_laps.empty:
                tel = drv_laps.get_telemetry()
                time_col = 'SessionTime' if 'SessionTime' in tel.columns else 'Date'
                if not tel.empty and 'X' in tel.columns and time_col in tel.columns:
                    tel_synced = tel[[time_col, 'X', 'Y']].copy()
                    tel_synced.set_index(time_col, inplace=True)
                    tel_synced = tel_synced[~tel_synced.index.duplicated(keep='first')]
                    tel_synced = tel_synced.reindex(timestamps, method='nearest').reset_index()
                    tel_synced.rename(columns={'index': 'SessionTime'}, inplace=True)
                    tel_synced['Driver'] = drv
                    df_list.append(tel_synced)
        except: pass
        
    status_text.text("Phase 4/4: Packaging Animation Frames & Saving...")
    if df_list:
        map_df = pd.concat(df_list, ignore_index=True).sort_values('SessionTime').fillna(0)
        for t_val, group in map_df.groupby('SessionTime'):
            t_sec = t_val.total_seconds()
            cars = {str(row['Driver']): [float(row['X']), float(row['Y'])] for _, row in group.iterrows()}
            payload["frames"].append({"t_sec": float(t_sec), "cars": cars})
        payload["frames"].sort(key=lambda x: x["t_sec"])
        
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    st.session_state['js_payload'] = payload
    st.session_state['replay_session_id'] = cache_path
    
    progress_bar.progress(1.0)
    status_text.success("✅ All data generated and cached successfully! Starting Replay...")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()

@st.fragment
def fragment_replay_continuous(session, year, round_num, session_code):
    st.subheader("Full Session Continuous")
    max_lap_avail = int(session.laps['LapNumber'].max()) if not session.laps.empty else 0
    if max_lap_avail == 0:
        st.warning("No lap data available for this session.")
        return

    cache_filename = f"replay_{year}_{round_num}_{session_code}.json"
    cache_path = os.path.join(CACHE_DIR, cache_filename)
    
    if 'js_payload' not in st.session_state or st.session_state.get('replay_session_id') != cache_path:
        if os.path.exists(cache_path):
            with st.spinner("Loading Replay package from local cache..."):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    st.session_state['js_payload'] = json.load(f)
                st.session_state['replay_session_id'] = cache_path
        else:
            st.info("Replay data is not cached yet. Generating it requires processing all telemetry points for 20 cars.")
            if st.button("Load & Generate Replay Data", type="primary"):
                generate_and_cache_replay_payload(session, max_lap_avail, cache_path)
                st.rerun(scope="fragment")
            return

    if 'js_payload' in st.session_state:
        payload_json = json.dumps(st.session_state['js_payload'])
        template_path = 'components/ReplayEngine.html'
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                html_template = f.read()
                
            html_code = html_template.replace('__PAYLOAD_JSON_PLACEHOLDER__', payload_json)
            components.html(html_code, height=1050, scrolling=True)
            
        except FileNotFoundError:
            st.error(f"⚠️ Không tìm thấy file HTML giao diện tại: {template_path}")

# ==========================================
# MULTI-PAGE DEFINITIONS
# ==========================================

def page_home_ui():
    col_title, col_sel = st.columns([3, 1])
    with col_title:
        st.title("🏎️ F1 Pulse")
        st.markdown("Explore race schedules, results, and in-depth performance analysis.")
    with col_sel:
        st.markdown("<br>", unsafe_allow_html=True)
        selected_year = st.selectbox("📅 Select Season:", [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018], index=[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018].index(st.session_state['selected_year']), label_visibility="collapsed")
        st.session_state['selected_year'] = selected_year

    st.divider()
    events_df = get_schedule(selected_year)

    if not events_df.empty:
        st.subheader(f"Race Calendar & Results - Season {selected_year}")
        for i in range(0, len(events_df), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(events_df):
                    event = events_df.iloc[i + j]
                    col = cols[j]
                    
                    round_num = event['RoundNumber']
                    event_name = event['EventName']
                    country = event['Country']
                    flag_url = get_flag_url(country)
                    
                    event_date = event['EventDate']
                    if pd.notna(event_date):
                        date_str = event_date.strftime("%d %b, %Y")
                        is_completed = event_date.tz_localize(None) < datetime.now()
                    else:
                        date_str = "TBA"; is_completed = False
                    
                    format_type = event.get('EventFormat', 'conventional').capitalize()
                    
                    with col:
                        with st.container(border=True):
                            st.markdown(f"<h4 style='margin-bottom:0;'><img src='{flag_url}' width='32' style='border-radius:4px; vertical-align:middle; margin-right:10px; box-shadow: 0 0 2px rgba(255,255,255,0.3);'> Round {round_num}</h4>", unsafe_allow_html=True)
                            st.markdown(f"**{event_name}**")
                            st.caption(f"📍 {event['Location']}, {country} | 🗓️ {date_str}")
                            st.divider()
                            
                            if is_completed:
                                st.markdown("🟢 **Status:** Completed")
                                winner = get_race_winner(selected_year, round_num)
                                st.markdown(f"🏆 **Winner:** {winner}")
                            else:
                                st.markdown("⏳ **Status:** Upcoming")
                                if format_type in ['Sprint', 'Sprint_qualifying']: st.markdown("🏎️ **Format:** Sprint Weekend")
                                else: st.markdown("🏎️ **Format:** Conventional")
                            
                            if st.button(f"Analyze", key=f"btn_{selected_year}_{round_num}", width='stretch', disabled=not is_completed):
                                st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                                st.switch_page(page_details)
    else:
        st.warning("No schedule data found for this season.")

def page_details_ui():
    if not st.session_state.get('selected_event'):
        st.warning("Please select a race from the Calendar first.")
        if st.button("Return to Calendar"):
            st.switch_page(page_home)
        return

    event_info = st.session_state['selected_event']
    year, round_num, event_name, flag_url = event_info['year'], event_info['round'], event_info['name'], get_flag_url(event_info['country'])

    st.divider()
    col_back, col_title, col_session = st.columns([0.15, 3.5, 1.2])

    with col_back:
        st.write("") 
        if st.button("←", key="back_home_btn"):
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith(('ch_', 'sel_', 'del_', 'tel_', 'dom_')) or k in ['lt_boxes', 'lt_box_counter', 'sel_all_pos', 'replay_session_id', 'js_payload', 'predictions_race_id', 'predictions_df', 'gemini_insight', 'setup_profiler_fig']]
            for key in keys_to_clear:
                del st.session_state[key]
            st.switch_page(page_home)

    with col_title:
        st.markdown(f"<h2 style='margin-top: 0;'><img src='{flag_url}' width='48' style='border-radius:6px; vertical-align:middle; margin-right:15px; box-shadow: 0 0 4px rgba(255,255,255,0.3);'> {event_name} {year}</h2>", unsafe_allow_html=True)
    
    with col_session:
        schedule = fastf1.get_event_schedule(year)
        event_row = schedule[schedule['RoundNumber'] == round_num].iloc[0]
        format_type = event_row.get('EventFormat', 'conventional').lower()
        
        if format_type == 'sprint':
            available_sessions = ["Sprint", "Sprint Shootout", "Qualifying", "Race"]
            session_map = {"Sprint": "S", "Sprint Shootout": "SS", "Qualifying": "Q", "Race": "R"}
        elif format_type == 'sprint_qualifying': 
            available_sessions = ["Sprint Qualifying", "Sprint", "Qualifying", "Race"]
            session_map = {"Sprint Qualifying": "SQ", "Sprint": "S", "Qualifying": "Q", "Race": "R"}
        else:
            available_sessions = ["FP1", "FP2", "FP3", "Qualifying", "Race"]
            session_map = {"FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "Qualifying": "Q", "Race": "R"}

        selected_session_name = st.selectbox("Select Session:", available_sessions, index=len(available_sessions)-1, label_visibility="collapsed")
        session_code = session_map[selected_session_name]

    with st.spinner("Loading event highlights..."):
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

    with st.spinner(f"Loading session details for {selected_session_name}..."):
        session = load_f1_session(year, round_num, session_code)

    if session is not None:
        drivers = session.results['Abbreviation'].dropna().unique().tolist()

        tab_res, tab_pos, tab_strat, tab_laps, tab_dom, tab_tel, tab_predict, tab_replay = st.tabs([
            "📊 Results", "📈 Positions", "⏱️ Strategy", "⏱️ Lap Times", 
            "🗺️ Track Dominance", "📉 Telemetry", "✨ Race Predictor", "🎥 Replay"
        ])
        
        with tab_res:
            st.subheader(f"Results - {selected_session_name}")
            res_df = session.results.copy()
            formatted_times = []
            winner_time = pd.NaT
            if not res_df.empty and pd.notna(res_df.iloc[0]['Time']): winner_time = res_df.iloc[0]['Time']
                
            for index, row in res_df.iterrows():
                pos, time_val, status = row['Position'], row['Time'], str(row['Status'])
                if session_code in ['Q', 'SQ']:
                    best_q = row.get('Q3', pd.NaT)
                    if pd.isna(best_q): best_q = row.get('Q2', pd.NaT)
                    if pd.isna(best_q): best_q = row.get('Q1', pd.NaT)
                    if pd.notna(best_q):
                        q_sec = best_q.total_seconds()
                        formatted_times.append(f"{int(q_sec // 60):02d}:{int(q_sec % 60):02d}")
                    else: formatted_times.append(status)
                else:
                    if pd.isna(time_val): formatted_times.append(status)
                    elif pos == 1 or pd.isna(winner_time):
                        ts = time_val.total_seconds()
                        formatted_times.append(f"{int(ts // 3600):02d}:{int((ts % 3600) // 60):02d}:{int(ts % 60):02d}")
                    else:
                        gap = time_val.total_seconds()
                        formatted_times.append(f"+{int(gap // 60):02d}:{int(gap % 60):02d}")
            
            display_df = pd.DataFrame({
                'Pos': res_df['Position'].astype(str).str.replace('.0', '', regex=False),
                'Driver': res_df['FullName'], 'Team': res_df['TeamName'],
                'Grid': res_df['GridPosition'].astype(str).str.replace('.0', '', regex=False),
                'Status': res_df['Status'], 'Time': formatted_times,
                'Points': res_df['Points'].astype(str).str.replace('.0', '', regex=False)
            })
            st.dataframe(display_df.replace('nan', 'N/A'), width='stretch', hide_index=True)
            
        with tab_pos: fragment_positions(session, drivers, selected_session_name)
            
        with tab_strat:
            sub_overview, sub_stint = st.tabs(["📊 Strategy Overview", "📋 Stint Detail Analysis"])
            all_laps = session.laps.copy().dropna(subset=['Stint', 'Compound'])
            compound_colors = {'SOFT': '#FF3333', 'MEDIUM': '#FFF200', 'HARD': '#FFFFFF', 'INTERMEDIATE': '#39B54A', 'WET': '#00AEEF'}

            with sub_overview:
                st.subheader("Tire Strategy Timeline")
                finish_order = session.results['Abbreviation'].dropna().tolist()
                if not all_laps.empty:
                    stints = all_laps.groupby(['Driver', 'Stint', 'Compound']).agg(StartLap=('LapNumber', 'min'), EndLap=('LapNumber', 'max'), StintLength=('LapNumber', 'count')).reset_index()
                    stints['Driver'] = pd.Categorical(stints['Driver'], categories=finish_order, ordered=True)
                    fig_strat = px.bar(stints.sort_values(['Driver', 'Stint']), x='StintLength', y='Driver', color='Compound', color_discrete_map=compound_colors, orientation='h', labels={'Driver': 'Driver', 'StintLength': 'Laps'})
                    fig_strat.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Lap", height=max(500, len(finish_order)*30))
                    st.plotly_chart(fig_strat, width='stretch')

            with sub_stint:
                st.subheader("Stint Performance Analysis")
                stint_stats = []
                for (driver, stint, compound), group in all_laps.groupby(['Driver', 'Stint', 'Compound']):
                    valid = group.dropna(subset=['LapTime'])
                    fastest, avg, sigma, deg = "N/A", "N/A", "N/A", "N/A"
                    if not valid.empty:
                        fastest = f"{int(valid['LapTime'].min().total_seconds()//60):02d}:{valid['LapTime'].min().total_seconds()%60:06.3f}"
                        avg = f"{int(valid['LapTime'].mean().total_seconds()//60):02d}:{valid['LapTime'].mean().total_seconds()%60:06.3f}"
                        l_sec = valid['LapTime'].dt.total_seconds()
                        if len(l_sec) > 1: sigma = f"σ = {l_sec[l_sec <= l_sec.min()*1.05].std(ddof=0):.3f}s"
                        if len(valid.dropna(subset=['TyreLife'])) > 2:
                            try: deg = f"{np.polyfit(valid['TyreLife'], l_sec, 1)[0]:+.3f} s/lap"
                            except: pass
                    stint_stats.append({'Driver': driver, 'Stint': int(stint), 'Compound': compound, 'Length': f"{len(group)} (L{int(group['LapNumber'].min())}-L{int(group['LapNumber'].max())})", 'Fastest': fastest, 'Average': avg, 'Consistency': sigma, 'Degradation': deg})
                st.dataframe(pd.DataFrame(stint_stats).sort_values(['Driver', 'Stint']), width='stretch', hide_index=True)
            
        with tab_laps: fragment_lap_times(session, drivers)
        with tab_dom: fragment_dominance(session, drivers)
        with tab_tel:
            st.subheader("Comprehensive Telemetry Analysis")
            st.divider()
            charts = [
                {'title': 'Speed Trace', 'metric': 'Speed', 'type': 'line', 'unit': 'km/h'},
                {'title': 'Gear Shifts', 'metric': 'nGear', 'type': 'map', 'unit': ''},
                {'title': 'Throttle Input', 'metric': 'Throttle', 'type': 'line', 'unit': '%'},
                {'title': 'Brake Input', 'metric': 'Brake', 'type': 'line', 'unit': ''},
                {'title': 'RPM', 'metric': 'RPM', 'type': 'line', 'unit': 'RPM'},
                {'title': 'DRS Usage', 'metric': 'DRS', 'type': 'line', 'unit': 'State'}
            ]
            for i in range(0, 6, 2):
                cols = st.columns(2)
                for j in range(2):
                    idx = i + j
                    with cols[j]: fragment_telemetry_card(session, drivers, charts[idx], idx)

        # ==========================================
        # Race Predictor Tab (Cập nhật tương thích với MLCore mới)
        # ==========================================
        with tab_predict:
            st.subheader("Pre-Race Podium Probability Predictor")
            
            current_race_id = f"{year}_{round_num}"
            if st.session_state.get('predictions_race_id') != current_race_id:
                st.session_state.pop('predictions_df', None)
                st.session_state.pop('setup_profiler_fig', None)
                st.session_state.pop('gemini_insight', None)
            
            # Đọc Gemini API Key từ file
            gemini_key = ""
            key_file_path = "assets/gemini_key.txt"
            if os.path.exists(key_file_path):
                with open(key_file_path, "r", encoding="utf-8") as f:
                    gemini_key = f.read().strip()
            
            gemini_client = None
            if gemini_key:
                gemini_client = genai.Client(api_key=gemini_key)
            
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                run_ai = st.button("Generate Predictions & Analysis", type="primary", use_container_width=True)
            with col_btn2:
                # Gọi hàm từ MLCore để train lại nếu cần
                retrain_ai = st.button("Retrain Model (If fresh data exists)", use_container_width=True)
                
            if retrain_ai:
                with st.spinner("Retraining the model from historical data..."):
                    ml_core.initialize_model(force_retrain=True)
                    st.success("Model retrained successfully!")
                    
            if run_ai:
                with st.spinner("Running simulations and generating technical insights..."):
                    try:
                        # 1. Gọi Module 1 từ MLCore
                        model = ml_core.initialize_model(force_retrain=False) 
                        inference_df = ml_core.prepare_race_features(year, round_num) 
                        preds_df = ml_core.predict_podium_probabilities(model, inference_df) 
                        
                        st.session_state['predictions_df'] = preds_df
                        st.session_state['predictions_race_id'] = current_race_id
                        
                        # 2. Xây dựng Setup Profiler (Top Speed vs Average Speed)
                        setup_data = []
                        for _, row in preds_df.head(10).iterrows():
                            drv = row['Driver']
                            try:
                                drv_lap = session.laps.pick_drivers(drv).pick_fastest()
                                if not pd.isna(drv_lap['LapTime']):
                                    tel = drv_lap.get_telemetry()
                                    if not tel.empty and 'Speed' in tel.columns:
                                        setup_data.append({
                                            'Driver': drv,
                                            'FullName': row['FullName'],
                                            'Top Speed (km/h)': tel['Speed'].max(),
                                            'Average Speed (km/h)': tel['Speed'].mean(),
                                            'Color': row['Color']
                                        })
                            except: pass
                                
                        if setup_data:
                            setup_df = pd.DataFrame(setup_data)
                            avg_x = setup_df['Average Speed (km/h)'].mean()
                            avg_y = setup_df['Top Speed (km/h)'].mean()

                            fig_setup = px.scatter(
                                setup_df, x='Average Speed (km/h)', y='Top Speed (km/h)',
                                text='Driver', color='Driver',
                                color_discrete_map={r['Driver']: r['Color'] for _, r in setup_df.iterrows()}
                            )
                            fig_setup.update_traces(textposition='top center', marker=dict(size=14, line=dict(width=1, color='White')))
                            
                            # Add the Profiler Cross (Axes)
                            fig_setup.add_vline(x=avg_x, line_dash="dash", line_color="rgba(255,255,255,0.3)")
                            fig_setup.add_hline(y=avg_y, line_dash="dash", line_color="rgba(255,255,255,0.3)")

                            # Add Quadrant Labels
                            # Top Right
                            fig_setup.add_annotation(xref="paper", yref="paper", x=0.95, y=0.95, text="<b>Efficient</b><br>(High DF / Low Drag)", showarrow=False, font=dict(color="#00cc66", size=11), align="right")
                            # Bottom Right
                            fig_setup.add_annotation(xref="paper", yref="paper", x=0.95, y=0.05, text="<b>High Drag</b><br>(Downforce Focused)", showarrow=False, font=dict(color="#ff4b4b", size=11), align="right")
                            # Top Left
                            fig_setup.add_annotation(xref="paper", yref="paper", x=0.05, y=0.95, text="<b>Low Drag</b><br>(Speed Focused)", showarrow=False, font=dict(color="#00ccff", size=11), align="left")
                            # Bottom Left
                            fig_setup.add_annotation(xref="paper", yref="paper", x=0.05, y=0.05, text="<b>Inefficient</b><br>(Low DF / High Drag)", showarrow=False, font=dict(color="#888", size=11), align="left")

                            fig_setup.update_layout(
                                title=dict(text="🏎️ Setup Profiler (Downforce vs Drag)", font=dict(size=16)),
                                xaxis_title="Average Speed (Higher = Better Downforce)",
                                yaxis_title="Top Speed (Higher = Lower Drag)",
                                showlegend=False, height=500,
                                plot_bgcolor='rgba(20,20,20,0.5)', paper_bgcolor='rgba(0,0,0,0)',
                                margin=dict(l=0, r=0, t=50, b=0),
                                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)")
                            )
                            st.session_state['setup_profiler_fig'] = fig_setup
                        
                        # 3. Prompt Gemini chuyên sâu về kỹ thuật
                        if gemini_client:
                            prompt_data = preds_df.head(10)[['Driver', 'FullName', 'GridPosition', 'Podium_Probability', 'QualifyingDelta', 'FP2_PaceDelta']].to_string(index=False)
                            prompt = f"""
                            You are a world-class F1 Chief Race Engineer.
                            Analyze the following race simulation data for the {event_name} {year}. 
                            Do NOT mention AI or Machine Learning. Treat these values as internal engineering simulations.

                            SIMULATION DATA:
                            {prompt_data}

                            Requirements:
                            - Provide a highly technical tactical briefing (200-250 words) in English.
                            - Use clear bold headings and bullet points for readability.
                            - Focus on:
                                * Primary Contenders: Analyze favorites based on Qualifying Delta and simulation probabilities.
                                * Tactical 'Dark Horse': Identify a driver outside the Top 4 with strong long-run pace (FP2_PaceDelta) likely to challenge the podium.
                                * Strategic Implications: Impact of track position vs. race pace on pit window decisions.
                            - Tone: Strictly data-driven, precise, and professional.
                            """
                            response = gemini_client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt
                            )
                            st.session_state['gemini_insight'] = response.text
                        else:
                            st.session_state['gemini_insight'] = "⚠️ Gemini API Key not found in assets/gemini_key.txt."

                    except Exception as e:
                        st.error(f"Analysis error: {str(e)}")

            # --- HIỂN THỊ KẾT QUẢ ---
            if 'predictions_df' in st.session_state:
                predictions_df = st.session_state['predictions_df']
                st.divider()
                st.markdown("### Podium Probability Predictions")
                
                col_chart, col_setup = st.columns([1.2, 1])
                
                with col_chart:
                    # Sắp xếp tăng dần (True) để Plotly vẽ giá trị cao nhất lên ĐẦU trục Y
                    top_10_df = predictions_df.head(10).sort_values('Podium_Probability', ascending=True)
                    fig_pred = px.bar(
                        top_10_df, 
                        x='Podium_Probability', 
                        y='Driver',
                        orientation='h',
                        color='Driver',
                        color_discrete_map={row['Driver']: row['Color'] for _, row in predictions_df.iterrows()},
                        text=top_10_df['Podium_Probability'].apply(lambda x: f"{x:.1%}")
                    )
                    fig_pred.update_layout(
                        title=dict(text="Top 10 Probability Standings", font=dict(size=16)),
                        xaxis_title="Probability to Finish in Top 3",
                        yaxis_title="",
                        yaxis=dict(categoryorder='total ascending'),
                        xaxis=dict(tickformat=".0%", range=[0, 1]),
                        showlegend=False, height=500,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0, r=0, t=50, b=0)
                    )
                    fig_pred.update_traces(textposition='outside', cliponaxis=False)
                    st.plotly_chart(fig_pred, width='stretch')
                
                with col_setup:
                    if 'setup_profiler_fig' in st.session_state:
                        st.plotly_chart(st.session_state['setup_profiler_fig'], width='stretch')
                    else:
                        st.info("Insufficient Telemetry data for Setup Profiler.")

                # Gemini Insight Section
                st.divider()
                st.markdown("### Tactical Analysis Assistant")
                if 'gemini_insight' in st.session_state:
                    # Hiển thị trực tiếp kết quả Markdown để giữ bullet points
                    st.markdown(st.session_state['gemini_insight'])

        # ==========================================
        with tab_replay:
            fragment_replay_continuous(session, year, round_num, session_code)
    else: 
        st.warning("Unable to load data for this session.")


# ==========================================
# MULTI-PAGE ROUTING
# ==========================================
page_home = st.Page(page_home_ui, title="Race Calendar", icon="📅", default=True)
page_details = st.Page(page_details_ui, title="Race Analysis", icon="🏎️")
pg = st.navigation([page_home, page_details], position="hidden")
pg.run()