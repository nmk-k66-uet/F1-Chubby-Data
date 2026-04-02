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
import streamlit.components.v1 as components 
import json

# --- PAGE CONFIG ---
st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    /* Nhắm vào các thẻ div sinh ra bởi st.columns */
    [data-testid="column"] > div {
        overflow: visible !important;
    }
    /* Ép menu dropdown của Selectbox đè lên trên và có thanh cuộn */
    div[data-baseweb="popover"] > div {
        max-height: 300px !important;
        overflow-y: auto !important;
    }
    /* Ẩn hoàn toàn Sidebar và nút mở Sidebar ở góc trên bên trái */
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    [data-testid="stSidebar"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

fastf1.Cache.enable_cache('f1_cache')
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
# CÁC KHỐI FRAGMENT CŨ (GIỮ NGUYÊN)
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

        if not selected_drivers: st.warning("👈 Please select at least one driver.")
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
            st.caption("Note: Battery Level and Steering Angle are not broadcasted publicly by the FIA. The grid displays Throttle, Brake, RPM, and DRS in independent cards.")
            
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
            if pd.isna(lap_data['LapTime']): st.warning("No telemetry.")
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
        except Exception as e: st.error(f"Lỗi vẽ biểu đồ: {str(e)}")


# ==========================================
# KHỐI REPLAY NATIVE (MƯỢT MÀ LIÊN TỤC 100%)
# ==========================================
@st.fragment
def fragment_replay_continuous(session):
    st.subheader("🏎️ Full Session Continuous Replay")
    st.caption("Dữ liệu toàn phiên được đóng gói chung thành 1 Timeline liên tục. Hoạt ảnh không bị khựng giữa các vòng đua.")
    
    session_id = f"{st.session_state.get('selected_year', '')}_{st.session_state.get('selected_event', {}).get('round', '')}"
    if 'replay_session_id' not in st.session_state or st.session_state['replay_session_id'] != session_id:
        st.session_state['replay_session_id'] = session_id
        st.session_state.pop('js_payload', None)

    max_lap_avail = int(session.laps['LapNumber'].max()) if not session.laps.empty else 0
    if max_lap_avail == 0:
        st.warning("Không có dữ liệu Lap cho phiên đua này.")
        return

    # 1. TIẾN TRÌNH PRE-LOAD (CHẠY 1 LẦN DUY NHẤT)
    if 'js_payload' not in st.session_state:
        st.warning("⏳ Đang tải luồng dữ liệu liên tục cho toàn bộ cuộc đua. Xin vui lòng chờ khoảng 1-2 phút...")
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        
        payload = {
            "frames": [], "laps_info": {}, "messages": [], "colors": {}, "track_path": [], 
            "max_lap": max_lap_avail, "min_x": 0, "max_x": 1, "min_y": 0, "max_y": 1
        }
        
        drivers = session.results['Abbreviation'].dropna().unique().tolist()
        for drv in drivers:
            info = session.get_driver(drv)
            payload["colors"][drv] = f"#{info['TeamColor']}" if str(info['TeamColor']) != 'nan' else '#FFFFFF'
            
        try:
            ref_tel = session.laps.pick_fastest().get_telemetry()
            payload["track_path"] = ref_tel[['X', 'Y']].dropna().values.tolist()
            payload["min_x"], payload["max_x"] = float(ref_tel['X'].min()), float(ref_tel['X'].max())
            payload["min_y"], payload["max_y"] = float(ref_tel['Y'].min()), float(ref_tel['Y'].max())
        except: pass
        
        # Lấy Thông điệp Race Control
        rcm_df = session.race_control_messages
        if not rcm_df.empty:
            for _, row in rcm_df.iterrows():
                t_val = row['Time']
                try:
                    if pd.api.types.is_datetime64_any_dtype(type(t_val)):
                        if hasattr(session, 't0_date') and session.t0_date is not None:
                            t_sec = (t_val.tz_localize(None) - session.t0_date.tz_localize(None)).total_seconds()
                        else: t_sec = 0
                        time_str = t_val.strftime("%H:%M:%S")
                    else:
                        t_sec = t_val.total_seconds()
                        time_str = f"T+{int(t_sec//60):02d}:{int(t_sec%60):02d}"
                        
                    payload["messages"].append({
                        "t_sec": float(t_sec), "time_str": time_str,
                        "flag": str(row['Flag']), "msg": str(row['Message'])
                    })
                except: pass
                
        # Lấy Bảng Timing cho TỪNG vòng (để JS update liên tục)
        status_text.text("Đang trích xuất dữ liệu Live Timing...")
        for lap in range(1, max_lap_avail + 1):
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
            
            # Lưu thời điểm mà vòng này KẾT THÚC (tay đua đầu tiên qua vạch)
            end_t = leader_time.total_seconds() if pd.notna(leader_time) else session.laps['Time'].max().total_seconds()
            payload["laps_info"][str(lap)] = {"timing": timing_data, "end_t_sec": float(end_t)}

        # Gộp chung Telemetry của TOÀN BỘ phiên đua thành 1 luồng liên tục
        status_text.text("Đang nội suy quỹ đạo xe (Continuous Timeline)...")
        min_time = session.laps['LapStartTime'].dropna().min()
        max_time = session.laps['Time'].dropna().max()
        timestamps = pd.timedelta_range(start=min_time, end=max_time, freq='1S') # Cập nhật vị trí mỗi 1 giây
        
        df_list = []
        for i, drv in enumerate(drivers):
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
            progress_bar.progress((i + 1) / len(drivers))
            
        status_text.text("Đang đóng gói Animation Frames...")
        if df_list:
            map_df = pd.concat(df_list, ignore_index=True).sort_values('SessionTime').fillna(0)
            for t_val, group in map_df.groupby('SessionTime'):
                t_sec = t_val.total_seconds()
                cars = {str(row['Driver']): [float(row['X']), float(row['Y'])] for _, row in group.iterrows()}
                payload["frames"].append({"t_sec": float(t_sec), "cars": cars})
            payload["frames"].sort(key=lambda x: x["t_sec"])
            
        st.session_state['js_payload'] = payload
        status_text.success("✅ Toàn bộ dữ liệu đã được nạp và đóng gói! Đang khởi động Player...")
        time.sleep(1.5)
        status_text.empty()
        progress_bar.empty()
        st.rerun()

    # 2. XUẤT GIAO DIỆN CHẠY BẰNG NATIVE JS
    if 'js_payload' in st.session_state:
        payload_json = json.dumps(st.session_state['js_payload'])
        
        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ background-color: rgba(0,0,0,0); color: #fff; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; overflow: hidden; }}
                .container {{ display: flex; flex-direction: column; height: 820px; background: #0e1117; border-radius: 8px; border: 1px solid #333; }}
                
                /* HÀNG 1: MAP */
                .map-row {{ flex: 1.2; position: relative; background: #000; border-bottom: 1px solid #333; min-height: 400px; }}
                canvas {{ display: block; width: 100%; height: 100%; }}
                .controls {{ position: absolute; bottom: 10px; left: 10px; right: 10px; background: rgba(20,20,20,0.8); padding: 10px 15px; border-radius: 6px; display: flex; align-items: center; gap: 15px; border: 1px solid #444; }}
                button {{ background: #ff4b4b; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; min-width: 90px;}}
                button:hover {{ background: #ff3333; }}
                input[type=range] {{ flex: 1; cursor: pointer; accent-color: #ff4b4b; }}
                .lap-badge {{ position: absolute; top: 15px; left: 15px; background: rgba(0,0,0,0.7); padding: 8px 15px; border-radius: 6px; font-size: 20px; font-weight: bold; color: #ff4b4b; border: 1px solid #333; }}
                
                /* HÀNG 2: DỮ LIỆU */
                .data-row {{ display: flex; height: 350px; background: #0e1117; }}
                .timing-col {{ flex: 6; overflow-y: auto; border-right: 1px solid #333; }}
                .msg-col {{ flex: 4; overflow-y: auto; padding: 15px; background: #11141a; }}
                
                /* BẢNG TIMING */
                table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
                thead {{ position: sticky; top: 0; background: #1a1c23; z-index: 10; box-shadow: 0 1px 2px rgba(0,0,0,0.5); }}
                th {{ padding: 10px; color: #aaa; text-transform: uppercase; text-align: left; }}
                td {{ padding: 8px 10px; border-bottom: 1px solid #222; }}
                tr:hover {{ background: rgba(255,255,255,0.05); }}
                
                /* BẢNG MESSAGE */
                .msg-header {{ color: #888; font-size: 12px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 8px; position: sticky; top: 0; background: #11141a;}}
                .msg-item {{ margin-bottom: 6px; font-size: 13px; padding: 8px; border-radius: 4px; border-left: 4px solid #444; }}
                .msg-Yellow {{ background: rgba(255, 255, 0, 0.1); border-left-color: yellow; }}
                .msg-Red {{ background: rgba(255, 0, 0, 0.1); border-left-color: red; }}
                .msg-Green {{ background: rgba(0, 255, 0, 0.1); border-left-color: #00cc66; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="map-row">
                    <canvas id="trackCanvas"></canvas>
                    <div class="lap-badge" id="lapBadge">LAP 1</div>
                    <div class="controls">
                        <button id="playBtn">▶ Play</button>
                        <input type="range" id="progressSlider" min="0" max="100" value="0" step="1">
                    </div>
                </div>
                <div class="data-row">
                    <div class="timing-col">
                        <table>
                            <thead><tr><th>P</th><th>Driver</th><th>Gap to Leader</th><th>Last Lap</th><th>Tyre</th></tr></thead>
                            <tbody id="timing-body"></tbody>
                        </table>
                    </div>
                    <div class="msg-col">
                        <div class="msg-header">🚨 Race Control Messages</div>
                        <div id="msgBoard"></div>
                    </div>
                </div>
            </div>

            <script>
                const payload = {payload_json};
                const canvas = document.getElementById('trackCanvas');
                const ctx = canvas.getContext('2d');
                const playBtn = document.getElementById('playBtn');
                const slider = document.getElementById('progressSlider');
                const lapBadge = document.getElementById('lapBadge');
                
                let currentFrameIdx = 0;
                let currentLap = 0;
                let isPlaying = false;
                
                if (payload.frames && payload.frames.length > 0) {{
                    slider.max = payload.frames.length - 1;
                }}
                
                // Thuật toán co giãn bản đồ vừa khung
                let scale = 1, offsetX = 0, offsetY = 0;
                function resizeCanvas() {{
                    canvas.width = canvas.parentElement.clientWidth;
                    canvas.height = canvas.parentElement.clientHeight;
                    const padding = 40;
                    const cw = canvas.width - padding * 2;
                    const ch = canvas.height - padding * 2;
                    const tw = payload.max_x - payload.min_x;
                    const th = payload.max_y - payload.min_y;
                    if(tw > 0 && th > 0) {{
                        scale = Math.min(cw / tw, ch / th);
                        offsetX = (canvas.width - tw * scale) / 2 - payload.min_x * scale;
                        offsetY = (canvas.height - th * scale) / 2 - payload.min_y * scale;
                    }}
                    drawFullFrame();
                }}
                window.addEventListener('resize', resizeCanvas);
                
                function getX(x) {{ return x * scale + offsetX; }}
                function getY(y) {{ return canvas.height - (y * scale + offsetY); }}
                
                function drawTrack() {{
                    if(!payload.track_path || payload.track_path.length === 0) return;
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                    ctx.lineWidth = 10;
                    ctx.lineCap = 'round';
                    ctx.lineJoin = 'round';
                    for(let i=0; i<payload.track_path.length; i++) {{
                        let [x, y] = payload.track_path[i];
                        if(i===0) ctx.moveTo(getX(x), getY(y));
                        else ctx.lineTo(getX(x), getY(y));
                    }}
                    ctx.stroke();
                }}
                
                function drawCars(cars) {{
                    for (let drv in cars) {{
                        let [x, y] = cars[drv];
                        let cx = getX(x), cy = getY(y);
                        
                        ctx.fillStyle = payload.colors[drv] || '#FFF';
                        ctx.beginPath();
                        ctx.arc(cx, cy, 7, 0, 2*Math.PI);
                        ctx.fill();
                        
                        ctx.lineWidth = 1.5;
                        ctx.strokeStyle = '#000';
                        ctx.stroke();
                        
                        ctx.fillStyle = "white";
                        ctx.font = "bold 11px Arial";
                        ctx.fillText(drv, cx + 10, cy + 4);
                    }}
                }}
                
                // Đồng bộ hóa Dữ liệu theo Tọa độ Thời gian thực
                function syncDataByTime(t_sec) {{
                    let newLap = 1;
                    for (let i = 1; i <= payload.max_lap; i++) {{
                        let lapStr = i.toString();
                        if (payload.laps_info[lapStr] && t_sec <= payload.laps_info[lapStr].end_t_sec) {{
                            newLap = i; break;
                        }}
                        newLap = i; // Khóa ở vòng cuối cùng
                    }}
                    
                    if (newLap !== currentLap || document.getElementById('timing-body').innerHTML === '') {{
                        currentLap = newLap;
                        lapBadge.innerText = "LAP " + currentLap;
                        
                        const lapData = payload.laps_info[currentLap.toString()];
                        if(lapData && lapData.timing) {{
                            let html = '';
                            lapData.timing.forEach(row => {{
                                const color = payload.colors[row.drv] || '#FFF';
                                html += `<tr>
                                    <td><b>${{row.pos}}</b></td>
                                    <td style="color:${{color}}; font-weight:bold;">${{row.drv}}</td>
                                    <td>${{row.gap}}</td>
                                    <td style="font-family:monospace;">${{row.last_lap}}</td>
                                    <td>${{row.tyre}}</td>
                                </tr>`;
                            }});
                            document.getElementById('timing-body').innerHTML = html;
                        }}
                    }}
                    
                    // Update Messages
                    const validMsgs = payload.messages.filter(m => m.t_sec <= t_sec);
                    validMsgs.sort((a,b) => b.t_sec - a.t_sec);
                    const mbody = document.getElementById('msgBoard');
                    let html = '';
                    validMsgs.forEach(m => {{
                        let cls = 'msg-item';
                        if(m.flag.includes('Yellow') || m.flag.includes('SC')) cls += ' msg-Yellow';
                        else if(m.flag.includes('Red')) cls += ' msg-Red';
                        else if(m.flag.includes('Green') || m.flag.includes('Clear')) cls += ' msg-Green';
                        html += `<div class="${{cls}}"><span class="msg-time">${{m.time_str}}</span> | ${{m.flag}} - ${{m.msg}}</div>`;
                    }});
                    if(html === '') html = '<div style="color:#666;">No incidents reported yet.</div>';
                    mbody.innerHTML = html;
                }}
                
                function drawFullFrame() {{
                    if(payload.frames.length === 0) return;
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    drawTrack();
                    
                    const frame = payload.frames[currentFrameIdx];
                    if(frame) {{
                        drawCars(frame.cars);
                        syncDataByTime(frame.t_sec);
                    }}
                }}
                
                // GAME LOOP (30 FPS, tốc độ ~x30 lần thực tế)
                let lastTime = 0;
                const FPS_INTERVAL = 30; 
                
                function loop(timestamp) {{
                    if(isPlaying) {{
                        if (!lastTime) lastTime = timestamp;
                        if (timestamp - lastTime >= FPS_INTERVAL) {{
                            lastTime = timestamp;
                            currentFrameIdx++;
                            if (currentFrameIdx >= payload.frames.length) {{
                                currentFrameIdx = payload.frames.length - 1;
                                isPlaying = false;
                                playBtn.innerText = "▶ Play";
                            }} else {{
                                slider.value = currentFrameIdx;
                                drawFullFrame();
                            }}
                        }}
                    }} else {{
                        lastTime = 0; // Đặt lại timer khi Pause
                    }}
                    requestAnimationFrame(loop);
                }}
                
                // Sự kiện
                playBtn.addEventListener('click', () => {{
                    if(payload.frames.length === 0) return;
                    isPlaying = !isPlaying;
                    playBtn.innerText = isPlaying ? "⏸ Pause" : "▶ Play";
                    if(isPlaying && currentFrameIdx >= payload.frames.length - 1) {{
                        currentFrameIdx = 0;
                    }}
                }});
                
                slider.addEventListener('input', (e) => {{
                    currentFrameIdx = parseInt(e.target.value);
                    drawFullFrame();
                }});
                
                // Khởi chạy vòng lặp
                setTimeout(() => {{
                    resizeCanvas();
                    if(payload.frames && payload.frames.length > 0) {{
                        drawFullFrame();
                        requestAnimationFrame(loop); // ĐÃ SỬA LỖI: Lệnh này kích hoạt Auto-play!
                    }}
                }}, 100);
            </script>
        </body>
        </html>
        """
        
        components.html(html_code, height=850)

# ==========================================
# CÁC TRANG CỦA ỨNG DỤNG (MULTI-PAGE DEFINITIONS)
# ==========================================

def page_home_ui():
    col_title, col_sel = st.columns([3, 1])
    with col_title:
        st.title("🏎️ F1 Pulse")
        st.markdown("Explore race schedules, results, and in-depth performance analysis.")
    with col_sel:
        st.markdown("<br>", unsafe_allow_html=True)
        selected_year = st.selectbox("📅 Select Season:", [2026, 2025, 2024, 2023, 2022, 2021], index=[2026, 2025, 2024, 2023, 2022, 2021].index(st.session_state['selected_year']), label_visibility="collapsed")
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
                            
                            # XỬ LÝ CHUYỂN TRANG
                            if st.button(f"Analyze", key=f"btn_{selected_year}_{round_num}", width='stretch', disabled=not is_completed):
                                st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                                st.switch_page(page_details)
    else:
        st.warning("No schedule data found for this season.")

def page_details_ui():
    if not st.session_state.get('selected_event'):
        st.warning("Vui lòng chọn một chặng đua từ Lịch thi đấu trước.")
        if st.button("Trở về Lịch thi đấu"):
            st.switch_page(page_home)
        return

    event_info = st.session_state['selected_event']
    year, round_num, event_name, flag_url = event_info['year'], event_info['round'], event_info['name'], get_flag_url(event_info['country'])

    st.divider()
    col_back, col_title, col_session = st.columns([0.15, 3.5, 1.2])

    with col_back:
        st.write("") 
        if st.button("←", key="back_home_btn"):
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith(('ch_', 'sel_', 'del_', 'tel_', 'dom_')) or k in ['lt_boxes', 'lt_box_counter', 'sel_all_pos', 'replay_session_id', 'js_payload']]
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

        tab_res, tab_pos, tab_strat, tab_laps, tab_dom, tab_tel, tab_replay = st.tabs([
            "📊 Results", "📈 Positions", "⏱️ Strategy", "⏱️ Lap Times", 
            "🗺️ Track Dominance", "📉 Telemetry", " 🎥 Replay"
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

        with tab_replay:
            fragment_replay_continuous(session)
    else: 
        st.warning("Unable to load data for this session.")


# ==========================================
# THIẾT LẬP NATIVE MULTI-PAGE ROUTING
# ==========================================
page_home = st.Page(page_home_ui, title="Race Calendar", icon="📅", default=True)
page_details = st.Page(page_details_ui, title="Race Analysis", icon="🏎️")
pg = st.navigation([page_home, page_details], position="hidden")
pg.run()