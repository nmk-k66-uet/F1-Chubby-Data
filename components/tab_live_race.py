"""
Live Race Tab Component - Real-time Race Updates and Analysis

Data sources:
  - InfluxDB `predictions` measurement (production: Spark slow path writes here)
  - Model Serving API HTTP fallback (when InfluxDB has no predictions)
  - FastF1 session.laps for historical replay simulation

Does NOT import ml_core or joblib.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import requests as _requests
import altair as alt
import plotly.graph_objects as go
from datetime import datetime, timezone

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


def _get_influx_client():
    """Create a reusable InfluxDB client. Returns (client, query_api) or (None, None)."""
    if not INFLUXDB_TOKEN:
        return None, None
    try:
        from influxdb_client import InfluxDBClient
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        return client, client.query_api()
    except Exception:
        return None, None


def _is_influx_reachable():
    """Ping InfluxDB health endpoint. Returns True if the service is up."""
    try:
        resp = _requests.get(f"{INFLUXDB_URL}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _fetch_live_timing_from_influxdb(race_id):
    """
    Query InfluxDB live_timing measurement for the latest lap snapshot.
    Returns (DataFrame, lap_number, total_data_available) or (None, 0, False).
    """
    client, query_api = _get_influx_client()
    if client is None:
        return None, 0, False
    try:
        flux = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "live_timing" and r.race_id == "{race_id}")
          |> last()
          |> pivot(rowKey:["_time", "driver"], columnKey: ["_field"], valueColumn: "_value")
        '''
        tables = query_api.query(flux)
        rows = []
        for table in tables:
            for record in table.records:
                rows.append({
                    "Driver": record.values.get("driver", ""),
                    "CurrentPosition": int(record.values.get("position", 20)),
                    "GapToLeader": float(record.values.get("gap_to_leader", 0)),
                    "Interval": float(record.values.get("interval", 0)),
                    "LapTimeMs": int(record.values.get("lap_time_ms", 0)),
                    "Compound": str(record.values.get("compound", "MEDIUM")),
                    "TyreLife": int(record.values.get("tyre_life", 0)),
                    "CompoundIdx": int(record.values.get("compound_idx", 1)),
                    "IsPitOut": int(record.values.get("is_pit_out", 0)),
                    "LapNumber": int(record.values.get("lap_number", 0)),
                    "LapFraction": float(record.values.get("lap_fraction", 0)),
                    "_time": record.get_time(),
                })
        client.close()
        if not rows:
            return None, 0, False
        df = pd.DataFrame(rows).sort_values("CurrentPosition")
        lap_number = int(df["LapNumber"].max())
        return df, lap_number, True
    except Exception:
        if client:
            client.close()
        return None, 0, False


def _fetch_predictions_from_influxdb(race_id):
    """Query InfluxDB for the latest pre-computed predictions. Returns (list of dicts, timestamp) or (None, None)."""
    client, query_api = _get_influx_client()
    if client is None:
        return None, None
    try:
        flux = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "predictions" and r.race_id == "{race_id}")
          |> last()
          |> pivot(rowKey:["_time", "driver"], columnKey: ["_field"], valueColumn: "_value")
        '''
        tables = query_api.query(flux)
        results = []
        latest_ts = None
        for table in tables:
            for record in table.records:
                ts = record.get_time()
                if latest_ts is None or (ts and ts > latest_ts):
                    latest_ts = ts
                results.append({
                    "driver": record.values.get("driver", ""),
                    "win_prob": float(record.values.get("win_prob", 0)),
                    "podium_prob": float(record.values.get("podium_prob", 0)),
                    "lap_number": int(record.values.get("lap_number", 0)),
                    "timestamp": ts,
                })
        client.close()
        return (results, latest_ts) if results else (None, None)
    except Exception:
        if client:
            client.close()
        return None, None

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


def _data_age_seconds(df):
    """Return the age in seconds of the most recent _time in the dataframe, or None."""
    if df is None or df.empty or "_time" not in df.columns:
        return None
    latest = df["_time"].max()
    if latest is None or pd.isna(latest):
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - latest).total_seconds()


def _is_race_in_past(session):
    """Check if the race date is in the past (historical race)."""
    try:
        event_date = session.event["EventDate"]
        if pd.isna(event_date):
            return False
        if hasattr(event_date, "tzinfo") and event_date.tzinfo is not None:
            return event_date < datetime.now(timezone.utc)
        return event_date < datetime.now()
    except Exception:
        return False


def _staleness_badge(pred_ts):
    """Return (label, color) for the prediction staleness indicator."""
    if pred_ts is None:
        return "No data", "#6c757d"
    age = (datetime.now(timezone.utc) - pred_ts).total_seconds()
    if age > 30:
        return f"Stale ({int(age)}s)", "#dc3545"  # red
    if age > 15:
        return f"Delayed ({int(age)}s)", "#ffc107"  # yellow
    return "Live", "#28a745"  # green


@st.fragment(run_every=3)
def fragment_live_race(session):
    """
    Renders the Live Race tab with real-time race information.
    
    Data flow:
    - InfluxDB live_timing (fast path) + predictions (slow path)
    - Shows offline status when InfluxDB is unreachable
    
    Updates every 3 seconds using @st.fragment(run_every=3).
    
    Args:
        session: FastF1 race session object (used for total lap count).
    """
    # === CSS STYLING FOR LIVE INDICATOR ===
    st.markdown("""
        <style>
        .live-header { color: #ff4b4b; font-weight: 800; animation: blink 2s infinite; }
        @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.5;} 100% {opacity: 1;} }
        .stExpander { border: 1px solid rgba(255,255,255,0.1) !important; border-radius: 8px !important; background: #121418 !important;}
        .source-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold; color:#fff; }
        </style>
    """, unsafe_allow_html=True)

    year = st.session_state['selected_event']['year']
    event = st.session_state['selected_event']['name']
    race_id = f"{year}_{event}"

    # ==========================================
    # 1. CONNECTION & DATA STATUS (separated)
    # ==========================================
    influx_up = _is_influx_reachable()

    if not influx_up:
        # ── STATE A: InfluxDB is down ──
        st.markdown("""
            <div style='text-align:center; padding:60px 20px;'>
                <span class='source-badge' style='background:#dc3545; font-size:14px;'>⚫ STREAM OFFLINE</span>
                <h3 style='margin-top:16px; color:#888;'>InfluxDB Unreachable</h3>
                <p style='color:#666;'>Cannot connect to the InfluxDB service.<br/>
                Ensure InfluxDB is running and accessible at <code>{}</code>.</p>
            </div>
        """.format(INFLUXDB_URL), unsafe_allow_html=True)
        return

    # InfluxDB is up — try to fetch data
    influx_df, influx_lap, has_data = _fetch_live_timing_from_influxdb(race_id)

    total_laps_est = session.laps['LapNumber'].max() if not session.laps.empty else 0
    total_laps = int(total_laps_est) if pd.notna(total_laps_est) else 0
    race_in_past = _is_race_in_past(session)

    if not has_data or influx_df is None or influx_df.empty:
        # ── STATE B: InfluxDB is up, but no data for this race ──
        st.markdown("""
            <div style='text-align:center; padding:10px;'>
                <span class='source-badge' style='background:#28a745; font-size:11px;'>● InfluxDB Connected</span>
            </div>
        """, unsafe_allow_html=True)

        if race_in_past:
            # Historical race — offer simulation
            st.markdown(f"""
                <div style='text-align:center; padding:40px 20px;'>
                    <span class='source-badge' style='background:#6c757d; font-size:14px;'>📊 NO SIMULATION DATA</span>
                    <h3 style='margin-top:16px; color:#888;'>{event}</h3>
                    <p style='color:#666;'>This race has already taken place but no live simulation data is available.<br/>
                    Run a simulation to replay the race with live timing and predictions.</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            # Future race — hasn't started
            st.markdown(f"""
                <div style='text-align:center; padding:40px 20px;'>
                    <span class='source-badge' style='background:#ffc107; font-size:14px; color:#000;'>⏳ RACE NOT STARTED</span>
                    <h3 style='margin-top:16px; color:#888;'>{event}</h3>
                    <p style='color:#666;'>This race hasn't happened yet.<br/>
                    Live timing data will appear here once the race begins and data is streamed.</p>
                </div>
            """, unsafe_allow_html=True)
        return

    # ── STATE C: InfluxDB is up AND has data ──
    live_lap_df = influx_df
    current_lap = influx_lap
    if total_laps == 0:
        total_laps = current_lap

    # Show connection status
    age = _data_age_seconds(influx_df)
    if age is not None and age > 120 and total_laps > 0 and current_lap >= total_laps:
        # Data is stale + final lap → finished
        age_str = f"{int(age // 60)}m ago" if age > 60 else f"{int(age)}s ago"
        st.markdown(f"""
            <div style='text-align:center; padding:10px;'>
                <span class='source-badge' style='background:#28a745; font-size:11px;'>● InfluxDB Connected</span>
                <span class='source-badge' style='background:#6c757d; font-size:11px; margin-left:8px;'>🏁 Race Finished ({age_str})</span>
            </div>
        """, unsafe_allow_html=True)
    elif age is not None and age > 120:
        # Data is stale but not final lap → stream interrupted
        st.markdown("""
            <div style='text-align:center; padding:10px;'>
                <span class='source-badge' style='background:#28a745; font-size:11px;'>● InfluxDB Connected</span>
                <span class='source-badge' style='background:#ffc107; font-size:11px; margin-left:8px; color:#000;'>⚠ Stream Stale</span>
            </div>
        """, unsafe_allow_html=True)
    else:
        # Fresh data → live
        st.markdown("""
            <div style='text-align:center; padding:10px;'>
                <span class='source-badge' style='background:#28a745; font-size:11px;'>● InfluxDB Connected</span>
                <span class='source-badge' style='background:#28a745; font-size:11px; margin-left:8px;'>📡 Live Stream</span>
            </div>
        """, unsafe_allow_html=True)

    # Ensure prob_history exists
    if 'prob_history' not in st.session_state:
        st.session_state['prob_history'] = pd.DataFrame(columns=['Lap', 'Driver', 'WinProb'])

    if live_lap_df.empty:
        st.info("Waiting for live timing data…")
        return

    # ==========================================
    # 2. LAYOUT: 2 columns (40% Timing, 60% ML)
    # ==========================================
    col_tower, col_predict = st.columns([1.2, 1.8], gap="large")

    # ==========================================
    # LEFT: LIVE TIMING TOWER (fast path)
    # ==========================================
    with col_tower:
        st.markdown("<span class='source-badge' style='background:#28a745;'>InfluxDB Live</span>", unsafe_allow_html=True)

        status_color = "red" if current_lap < total_laps else "gray"
        status_text = f"LAP {current_lap}/{total_laps}" if current_lap < total_laps else "🏁 FINISHED"
        st.markdown(f"<h3 class='live-header' style='color: {status_color}; margin-top:0;'>{status_text}</h3>", unsafe_allow_html=True)

        display_df = pd.DataFrame({
            "Pos": live_lap_df['CurrentPosition'].astype(int),
            "Driver": live_lap_df['Driver'],
            "Gap": ["Leader" if g == 0 else f"+{g:.3f}s" for g in live_lap_df['GapToLeader']],
            "Interval": ["-" if p == 1 else f"+{i:.3f}s" for p, i in zip(live_lap_df['CurrentPosition'], live_lap_df['Interval'])],
            "Tyre": live_lap_df['Compound'].astype(str).str[:1]
        })

        # Highlight P1/P2/P3 with podium colours
        podium_colors = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}  # gold, silver, bronze

        def _highlight_podium(row):
            pos = row["Pos"]
            if pos in podium_colors:
                bg = podium_colors[pos]
                return [f"background-color: {bg}; color: #000; font-weight: bold"] * len(row)
            return [""] * len(row)

        styled_df = display_df.head(20).style.apply(_highlight_podium, axis=1)
        st.dataframe(styled_df, hide_index=True, width='stretch', height=450)

    # ==========================================
    # RIGHT: ML INSPECTOR PANEL (slow path)
    # ==========================================
    with col_predict:
        st.markdown("<h3 style='margin-top:0;'>Live Predictor</h3>", unsafe_allow_html=True)

        # --- Predictions: InfluxDB → Model API → static fallback ---
        pred_source = "none"
        try:
            influx_preds, pred_ts = _fetch_predictions_from_influxdb(race_id)
            if influx_preds:
                pred_map = {p["driver"]: p for p in influx_preds}
                scored_df = live_lap_df.copy()
                scored_df["Live_Win_Prob"] = scored_df["Driver"].map(lambda d: pred_map.get(d, {}).get("win_prob", 0))
                scored_df["Live_Podium_Prob"] = scored_df["Driver"].map(lambda d: pred_map.get(d, {}).get("podium_prob", 0))
                scored_df = scored_df.sort_values(by=["Live_Win_Prob", "Live_Podium_Prob"], ascending=[False, False])
                pred_source = "influxdb"
            else:
                scored_df = _predict_via_api(live_lap_df)
                pred_source = "api"
                pred_ts = None
        except Exception:
            scored_df = live_lap_df.copy()
            scored_df['Live_Win_Prob'] = [0.65, 0.22, 0.05, 0.04, 0.04] + [0]*(len(scored_df)-5)
            scored_df['Live_Podium_Prob'] = [0.95, 0.85, 0.78, 0.40, 0.02] + [0]*(len(scored_df)-5)
            pred_ts = None

        # Staleness indicator
        if pred_source == "influxdb":
            stale_label, stale_color = _staleness_badge(pred_ts)
            st.markdown(f"<span class='source-badge' style='background:{stale_color};'>Predictions: {stale_label}</span>", unsafe_allow_html=True)
        elif pred_source == "api":
            st.markdown("<span class='source-badge' style='background:#17a2b8;'>Predictions: API Fallback</span>", unsafe_allow_html=True)

        # Update sparkline history
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