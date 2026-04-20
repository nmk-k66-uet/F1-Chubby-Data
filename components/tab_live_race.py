"""
Live Race Tab Component - Real-time Race Updates and Analysis

Data sources:
  - InfluxDB `predictions` measurement (production: Spark slow path writes here)
  - Model Serving API HTTP fallback (LOCAL_MODE or when InfluxDB has no data)
  - FastF1 session.laps for historical replay simulation

Does NOT import ml_core or joblib.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import time
import requests as _requests
import altair as alt
import plotly.graph_objects as go

MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://model-api:8080")
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "f1chubby")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "live_race")
LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() in ("1", "true", "yes")


def _predict_via_api(live_lap_df):
    """Call Model Serving API for in-race predictions. Returns df with Live_Win_Prob, Live_Podium_Prob."""
    try:
        drivers_payload = []
        for _, row in live_lap_df.iterrows():
            drivers_payload.append({
                "driver": str(row.get("Driver", "")),
                "LapFraction": float(row.get("LapFraction", 0)),
                "CurrentPosition": float(row.get("CurrentPosition", 20)),
                "GapToLeader": float(row.get("GapToLeader", 0)),
                "TyreLife": float(row.get("TyreLife", 0)),
                "CompoundIdx": float(row.get("CompoundIdx", 1)),
                "IsPitOut": float(row.get("IsPitOut", 0)),
            })
        resp = _requests.post(f"{MODEL_API_URL}/predict-inrace", json={"drivers": drivers_payload}, timeout=5)
        resp.raise_for_status()
        preds = {p["driver"]: p for p in resp.json()["predictions"]}

        live_lap_df["Live_Win_Prob"] = live_lap_df["Driver"].map(lambda d: preds.get(d, {}).get("win_prob", 0))
        live_lap_df["Live_Podium_Prob"] = live_lap_df["Driver"].map(lambda d: preds.get(d, {}).get("podium_prob", 0))
        return live_lap_df.sort_values(by=["Live_Win_Prob", "Live_Podium_Prob"], ascending=[False, False])
    except Exception:
        # Static fallback
        live_lap_df["Live_Win_Prob"] = [0.65, 0.22, 0.05, 0.04, 0.04] + [0] * max(0, len(live_lap_df) - 5)
        live_lap_df["Live_Podium_Prob"] = [0.95, 0.85, 0.78, 0.40, 0.02] + [0] * max(0, len(live_lap_df) - 5)
        return live_lap_df


def _fetch_predictions_from_influxdb(race_id, lap_number):
    """Query InfluxDB for pre-computed predictions. Returns list of dicts or None."""
    if not INFLUXDB_TOKEN or LOCAL_MODE:
        return None
    try:
        from influxdb_client import InfluxDBClient
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        query_api = client.query_api()
        flux = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "predictions" and r.race_id == "{race_id}")
          |> last()
          |> pivot(rowKey:["_time", "driver"], columnKey: ["_field"], valueColumn: "_value")
        '''
        tables = query_api.query(flux)
        results = []
        for table in tables:
            for record in table.records:
                results.append({
                    "driver": record.values.get("driver", ""),
                    "win_prob": record.values.get("win_prob", 0),
                    "podium_prob": record.values.get("podium_prob", 0),
                    "timestamp": record.get_time(),
                })
        client.close()
        return results if results else None
    except Exception:
        return None

def format_lap_time(td):
    """
    Formats a timedelta object into readable lap time format (MM:SS.sss).
    
    Args:
        td (pd.Timedelta or NaN): Lap time as timedelta object.
    
    Returns:
        str: Formatted lap time "MM:SS.sss" or "Pit / No Time" if unavailable.
    """
    if pd.isna(td): return "Pit / No Time"
    secs = td.total_seconds()
    mins = int(secs // 60)
    rem_secs = secs % 60
    return f"{mins}:{rem_secs:06.3f}"

def get_momentum(driver, current_prob):
    """
    Calculates the momentum (probability change) for a driver between recent laps.
    
    Args:
        driver (str): Driver abbreviation.
        current_prob (float): Current win probability (0-100).
    
    Returns:
        tuple: (momentum_text, color_code)
               - Text: "↗ +X.X%" (increasing), "↘ -X.X%" (decreasing), or "- 0.0%" (neutral)
               - Color: "#28a745" (green), "#dc3545" (red), or "#6c757d" (gray)
    """
    df_hist = st.session_state.get('prob_history', pd.DataFrame())
    if not df_hist.empty:
        drv_data = df_hist[df_hist['Driver'] == driver].sort_values('Lap')
        if len(drv_data) >= 2:
            prev_prob = drv_data.iloc[-2]['WinProb']
            diff = current_prob - prev_prob
            if diff > 0.1: return f"↗ +{diff:.1f}%", "#28a745"
            elif diff < -0.1: return f"↘ {diff:.1f}%", "#dc3545"
    return "- 0.0%", "#6c757d"

def render_sparkline(driver, color):
    """
    Renders a sparkline chart showing probability trend over laps for a driver.
    
    Args:
        driver (str): Driver abbreviation.
        color (str): Hex color code for the chart line and area fill.
    
    Output: Displays Altair area+line chart showing probability history.
    """
    df_hist = st.session_state.get('prob_history', pd.DataFrame())
    drv_data = df_hist[df_hist['Driver'] == driver].sort_values('Lap')
    
    if len(drv_data) < 2:
        st.markdown("<div style='color:gray; font-size:12px; margin-top:15px;'>Đang thu thập dữ liệu...</div>", unsafe_allow_html=True)
        return

    chart = alt.Chart(drv_data).mark_area(
        opacity=0.3, color=color, interpolate='monotone'
    ).encode(
        x=alt.X('Lap:Q', axis=None),
        y=alt.Y('WinProb:Q', scale=alt.Scale(domain=[0, 100]), axis=None),
        tooltip=['Lap', 'WinProb']
    ).properties(height=50)
    
    line = chart.mark_line(color=color, size=2.5)
    st.altair_chart(chart + line, width='stretch')

def render_radar(p1_row, p2_row):
    """
    Renders a radar (polar) chart comparing two drivers across 4 performance dimensions.
    
    Args:
        p1_row (pd.Series): First driver's live race metrics (Position, TyreLife, Gap, etc.)
        p2_row (pd.Series): Second driver's live race metrics.
    
    Metrics Plotted:
    - Pace Momentum: Based on compound type and tyre degradation
    - Tyre Health: Inverse of tyre life percentage
    - Track Position: Based on current race position
    - Gap Safety: Gap to leader
    
    Output: Displays interactive Plotly radar chart with two traces.
    """
    categories = ['Pace Momentum', 'Tyre Health', 'Track Position', 'Gap Safety']

    def calc_scores(row):
        pos = max(10, 100 - (row['CurrentPosition'] - 1) * 15)
        tyre = max(10, 100 - (row['TyreLife'] * 3))
        gap = 95 if row['CurrentPosition'] == 1 else max(10, 100 - (row['GapToLeader'] * 5))
        pace = 80 + (row['CompoundIdx'] * 5) - (row['TyreLife'] * 0.5)
        return [pace, tyre, pos, gap]

    fig = go.Figure()

    if p1_row is not None:
        fig.add_trace(go.Scatterpolar(
            r=calc_scores(p1_row), theta=categories, fill='toself',
            name=p1_row['Driver'], line_color='#4C78A8', fillcolor='rgba(76, 120, 168, 0.4)'
        ))
    if p2_row is not None:
        fig.add_trace(go.Scatterpolar(
            r=calc_scores(p2_row), theta=categories, fill='toself',
            name=p2_row['Driver'], line_color='#F58518', fillcolor='rgba(245, 133, 24, 0.4)'
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=False, range=[0, 100]),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#d0d0d0', size=11),
        margin=dict(l=30, r=30, t=20, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        height=260
    )
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


@st.fragment(run_every=3)
def fragment_live_race(session):
    """
    Renders the Live Race tab with real-time race information.
    
    Features:
    - Live timing table showing lap times and pit stop information
    - Win probability calculations for top drivers
    - Momentum indicators showing probability trends
    - Radar charts comparing selected drivers' performance
    - Sparkline history charts
    
    Updates every 3 seconds using @st.fragment(run_every=3).
    
    Args:
        session: FastF1 race session object with live lap data.
    """
    # === CSS STYLING FOR LIVE INDICATOR ===
    st.markdown("""
        <style>
        .live-header { color: #ff4b4b; font-weight: 800; animation: blink 2s infinite; }
        @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.5;} 100% {opacity: 1;} }
        .stExpander { border: 1px solid rgba(255,255,255,0.1) !important; border-radius: 8px !important; background: #121418 !important;}
        </style>
    """, unsafe_allow_html=True)
    
    # ==========================================
    # 1. TIỀN XỬ LÝ DỮ LIỆU HISTORICAL THÀNH STREAM 
    # ==========================================
    @st.cache_data(show_spinner=False)
    def prepare_stream_data(year, event_name):
        laps = session.laps.copy()
        if laps.empty: return pd.DataFrame(), 0
        
        total_laps = laps['LapNumber'].max()
        laps['CompoundIdx'] = laps['Compound'].map({'SOFT': 0, 'MEDIUM': 1, 'HARD': 2}).fillna(1)
        laps['IsPitOut'] = laps['PitOutTime'].notna().astype(int)
        laps['LapFraction'] = laps['LapNumber'] / total_laps
        
        leader_times = laps[laps['Position'] == 1].set_index('LapNumber')['Time']
        def calc_gap(row):
            if row['LapNumber'] in leader_times.index and pd.notna(row['Time']):
                gap = (row['Time'] - leader_times[row['LapNumber']]).total_seconds()
                return max(0.0, gap)
            return 0.0
            
        laps['GapToLeader'] = laps.apply(calc_gap, axis=1)
        laps.rename(columns={'Position': 'CurrentPosition'}, inplace=True)
        
        laps = laps.sort_values(['LapNumber', 'CurrentPosition'])
        laps['Interval'] = laps.groupby('LapNumber')['GapToLeader'].diff()
        laps.loc[laps['CurrentPosition'] == 1, 'Interval'] = 0.0
        laps['Interval'] = laps['Interval'].fillna(0.0).apply(lambda x: max(0.0, x))
        
        return laps, total_laps

    year = st.session_state['selected_event']['year']
    event = st.session_state['selected_event']['name']
    
    stream_df, total_laps = prepare_stream_data(year, event)
    if stream_df.empty:
        st.warning("Dữ liệu Telemetry vòng chạy (Laps) của chặng này không tồn tại hoặc chưa diễn ra.")
        return

    # ==========================================
    # 2. CƠ CHẾ ĐIỀU HƯỚNG LUỒNG 
    # ==========================================
    if 'sim_lap' not in st.session_state:
        st.session_state['sim_lap'] = 1.0 
        st.session_state['prob_history'] = pd.DataFrame(columns=['Lap', 'Driver', 'WinProb'])
        
    current_lap = int(st.session_state['sim_lap'])
    
    live_lap_df = stream_df[stream_df['LapNumber'] == current_lap].dropna(subset=['CurrentPosition']).copy()
    live_lap_df = live_lap_df.sort_values('CurrentPosition')
    
    if st.session_state['sim_lap'] < total_laps:
        st.session_state['sim_lap'] += 1

    # BỐ CỤC MỚI: 2 CỘT CHÍNH (40% cho Timing, 60% cho ML)
    col_tower, col_predict = st.columns([1.2, 1.8], gap="large")
    
    # ==========================================
    # PHÂN VÙNG TRÁI: LIVE TIMING TOWER
    # ==========================================
    with col_tower:
        status_color = "red" if current_lap < total_laps else "gray"
        status_text = f"LAP {current_lap}/{int(total_laps)}" if current_lap < total_laps else "🏁 FINISHED"
        st.markdown(f"<h3 class='live-header' style='color: {status_color}; margin-top:0;'>{status_text}</h3>", unsafe_allow_html=True)
        
        display_df = pd.DataFrame({
            "Pos": live_lap_df['CurrentPosition'].astype(int),
            "Driver": live_lap_df['Driver'],
            "Gap": [f"Leader" if g == 0 else f"+{g:.3f}s" for g in live_lap_df['GapToLeader']],
            "Interval": ["-" if p == 1 else f"+{i:.3f}s" for p, i in zip(live_lap_df['CurrentPosition'], live_lap_df['Interval'])],
            "Tyre": live_lap_df['Compound'].astype(str).str[:1]
        })
        st.dataframe(display_df.head(20), hide_index=True, width='stretch', height=450)

    # ==========================================
    # PHÂN VÙNG PHẢI: ML INSPECTOR PANEL
    # ==========================================
    with col_predict:
        st.markdown("<h3 style='margin-top:0;'>Live Predictor</h3>", unsafe_allow_html=True)
        
        # Chạy Model (via API or InfluxDB)
        try:
            # Try InfluxDB first (production: slow path writes predictions here)
            race_id = f"{year}_{event}"
            influx_preds = _fetch_predictions_from_influxdb(race_id, current_lap)
            if influx_preds:
                pred_map = {p["driver"]: p for p in influx_preds}
                scored_df = live_lap_df.copy()
                scored_df["Live_Win_Prob"] = scored_df["Driver"].map(lambda d: pred_map.get(d, {}).get("win_prob", 0))
                scored_df["Live_Podium_Prob"] = scored_df["Driver"].map(lambda d: pred_map.get(d, {}).get("podium_prob", 0))
                scored_df = scored_df.sort_values(by=["Live_Win_Prob", "Live_Podium_Prob"], ascending=[False, False])
            else:
                # Fallback: call Model Serving API directly
                scored_df = _predict_via_api(live_lap_df)
        except:
            # Static fallback
            scored_df = live_lap_df.copy()
            scored_df['Live_Win_Prob'] = [0.65, 0.22, 0.05, 0.04, 0.04] + [0]*(len(scored_df)-5)
            scored_df['Live_Podium_Prob'] = [0.95, 0.85, 0.78, 0.40, 0.02] + [0]*(len(scored_df)-5)

        # LƯU LỊCH SỬ ĐỂ VẼ SPARKLINE
        curr_laps = scored_df[['Driver', 'Live_Win_Prob']].copy()
        curr_laps['Lap'] = current_lap
        curr_laps['WinProb'] = curr_laps['Live_Win_Prob'] * 100
        
        st.session_state['prob_history'] = st.session_state['prob_history'][st.session_state['prob_history']['Lap'] != current_lap]
        st.session_state['prob_history'] = pd.concat([st.session_state['prob_history'], curr_laps[['Lap', 'Driver', 'WinProb']]])
        st.session_state['prob_history'] = st.session_state['prob_history'][st.session_state['prob_history']['Lap'] >= current_lap - 10]

        top_win = scored_df.sort_values('Live_Win_Prob', ascending=False).head(2)
        drv1 = top_win.iloc[0]['Driver'] if len(top_win) > 0 else None
        drv2 = top_win.iloc[1]['Driver'] if len(top_win) > 1 else None

        # [MODULE 1] WIN CONTENDERS (SPARKLINES)
        with st.expander("WIN CONTENDERS (Trend: Last 10 Laps)", expanded=True):
            if drv1:
                prob1 = top_win.iloc[0]['Live_Win_Prob'] * 100
                mom1, color1 = get_momentum(drv1, prob1)
                c_txt, c_chart = st.columns([1.5, 1])
                with c_txt:
                    st.markdown(f"**[ {drv1} ] {prob1:.1f}%** <span style='color:{color1}; font-size:13px; font-weight:bold;'>{mom1}</span>", unsafe_allow_html=True)
                    st.caption("📈 Impact: [+] Tyre  [+] Track Pos")
                with c_chart:
                    render_sparkline(drv1, '#4C78A8')
                    
            st.divider()
            
            if drv2:
                prob2 = top_win.iloc[1]['Live_Win_Prob'] * 100
                mom2, color2 = get_momentum(drv2, prob2)
                c_txt, c_chart = st.columns([1.5, 1])
                with c_txt:
                    st.markdown(f"**[ {drv2} ] {prob2:.1f}%** <span style='color:{color2}; font-size:13px; font-weight:bold;'>{mom2}</span>", unsafe_allow_html=True)
                    st.caption("📉 Impact: [-] Traffic [-] Gap Safety")
                with c_chart:
                    render_sparkline(drv2, '#F58518')

        # [MODULE 2] DYNAMIC RADAR
        with st.expander("BATTLE ANALYSIS", expanded=True):
            if drv1 and drv2:
                st.caption(f"Comparing Profiles: {drv1} vs {drv2}")
                p1_rt = live_lap_df[live_lap_df['Driver'] == drv1].iloc[0] if drv1 in live_lap_df['Driver'].values else None
                p2_rt = live_lap_df[live_lap_df['Driver'] == drv2].iloc[0] if drv2 in live_lap_df['Driver'].values else None
                render_radar(p1_rt, p2_rt)

        # [MODULE 3] PODIUM WATCH
        with st.expander("PODIUM WATCH (Next Contenders)", expanded=False):
            top_pod = scored_df[~scored_df['Driver'].isin([drv1, drv2])].sort_values('Live_Podium_Prob', ascending=False).head(3)
            for _, row in top_pod.iterrows():
                st.write(f"**{row['Driver']}** - {row['Live_Podium_Prob']*100:.1f}%")
                st.progress(int(row['Live_Podium_Prob']*100))
                
        if st.button("🔄 Restart Simulation", width='stretch'):
            st.session_state['sim_lap'] = 1.0
            st.session_state['prob_history'] = pd.DataFrame(columns=['Lap', 'Driver', 'WinProb'])
            st.rerun()