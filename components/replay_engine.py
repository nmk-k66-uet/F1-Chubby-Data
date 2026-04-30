import streamlit as st
import pandas as pd
import json
import os
import time
import logging
import streamlit.components.v1 as components

from core.data_loader import gcs, get_blob

logger = logging.getLogger(__name__)

GCS_CACHE_BUCKET = os.environ.get("GCS_CACHE_BUCKET", "f1chubby-cache")
CACHE_DIR = 'f1_cache'

"""Replay Engine Component - Interactive Race Replay Visualization

Provides a native JavaScript-based race replay engine showing:
- Live car positions and lap-by-lap movements on track map
- Race control messages and events timeline
- Real-time telemetry during replay (speed, throttle, brake, gear)
- Interactive playback controls

Data is generated from FastF1 telemetry and cached for performance.
"""

# ==========================================
# LAZY-LOADED REPLAY ENGINE (NATIVE JS)
# ==========================================
def generate_and_cache_replay_payload(session, max_lap_avail, cache_path, blob):
    """
    Generates and caches replay data payload from FastF1 session.
    
    This function extracts all necessary data from a race session to enable
    interactive replay visualization, including:
    - Track geometry and corner positions
    - Race control messages and flags
    - Car positions and telemetry for each lap
    
    Args:
        session: FastF1 session object with complete race data.
        max_lap_avail (int): Maximum lap number to process.
        cache_path (str): File path to save the cached JSON payload.
    
    Output: Creates JSON file with replay payload at cache_path
            Shows progress bar during data extraction (4 phases).
    
    Payload Structure:
    - frames: Array of lap telemetry frames for each driver
    - laps_info: Lap timing information
    - messages: Race control messages and flags
    - colors: Team colors for each driver
    - track_path: Track centerline coordinates [X, Y]
    - corners: Track corner positions and vectors
    - max_lap, min_x, max_x, min_y, max_y: Bounds information
    """
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
        
        # Track Geometry
        ref_lap = session.laps.pick_fastest()
        ref_tel = ref_lap.get_telemetry()
        full_track = ref_tel[['X', 'Y']].dropna().values.tolist()
        # Downsample track path — keep every 4th point (still smooth enough for rendering)
        payload["track_path"] = full_track[::4]
        payload["min_x"], payload["max_x"] = float(ref_tel['X'].min()), float(ref_tel['X'].max())
        payload["min_y"], payload["max_y"] = float(ref_tel['Y'].min()), float(ref_tel['Y'].max())
        
        # Finish Line Position
        payload["finish_line"] = [float(ref_tel['X'].iloc[0]), float(ref_tel['Y'].iloc[0])]
        
        # Start Line Position — try lap 1 telemetry, fall back to finish line
        start_found = False
        try:
            lap1_laps = session.laps[session.laps['LapNumber'] == 1].dropna(subset=['LapTime'])
            if not lap1_laps.empty:
                lap1_tel = lap1_laps.iloc[0].get_telemetry()
                if lap1_tel is not None and not lap1_tel.empty:
                    payload["start_line"] = [float(lap1_tel['X'].iloc[0]), float(lap1_tel['Y'].iloc[0])]
                    start_found = True
        except Exception:
            pass
        if not start_found:
            payload["start_line"] = payload["finish_line"]

        # Corners Vector — use track-local normal for reliable outward offset
        circuit_info = session.get_circuit_info()
        corners_data = []
        if circuit_info is not None and hasattr(circuit_info, 'corners'):
            center_x = (payload["min_x"] + payload["max_x"]) / 2
            center_y = (payload["min_y"] + payload["max_y"]) / 2
            track_pts = full_track  # use full-resolution track for accurate nearest-point lookup
            
            for _, row in circuit_info.corners.iterrows():
                cx = float(row['X']); cy = float(row['Y'])
                
                # Find nearest track point
                best_idx, best_dist = 0, float('inf')
                for i, pt in enumerate(track_pts):
                    d = (pt[0] - cx)**2 + (pt[1] - cy)**2
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
                
                # Track tangent at nearest point
                i_prev = (best_idx - 1) % len(track_pts)
                i_next = (best_idx + 1) % len(track_pts)
                tx = track_pts[i_next][0] - track_pts[i_prev][0]
                ty = track_pts[i_next][1] - track_pts[i_prev][1]
                
                # Perpendicular (two choices: (-ty, tx) or (ty, -tx))
                # Pick the one pointing away from track center
                nx, ny = -ty, tx
                dot_center = nx * (cx - center_x) + ny * (cy - center_y)
                if dot_center < 0:
                    nx, ny = ty, -tx
                
                mag = (nx**2 + ny**2)**0.5
                if mag == 0: mag = 1
                corners_data.append({
                    "x": cx, "y": cy, "nx": nx/mag, "ny": ny/mag, "number": str(row.get('Number', ''))
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
    timestamps = pd.timedelta_range(start=min_time, end=max_time, freq='500ms')
    
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
                    tel_synced = tel_synced.reindex(timestamps, method='nearest')
                    # Build per-driver arrays directly (avoid concat + groupby later)
                    df_list.append((drv, tel_synced['X'].values, tel_synced['Y'].values))
        except: pass
        
    status_text.text("Phase 4/4: Packaging Animation Frames & Saving...")
    if df_list:
        ts_seconds = [t.total_seconds() for t in timestamps]
        for idx, t_sec in enumerate(ts_seconds):
            cars = {}
            for drv, xs, ys in df_list:
                x_val = float(xs[idx]); y_val = float(ys[idx])
                if x_val != 0 or y_val != 0:
                    cars[drv] = [x_val, y_val]
            if cars:
                payload["frames"].append({"t_sec": t_sec, "cars": cars})
        
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)

    try:
        if gcs.available:
            file_name = cache_path.split("\\")[-1]
            gcs.upload_file(GCS_CACHE_BUCKET, blob_destination=blob + "/" + file_name, file_path=cache_path, content_type = "application/json")
    except Exception as e:
        logger.warning("Failed to upload replay JSON to GCS: %s", e)
        
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
    blob = get_blob(year, round_num, session_code)
    cache_path = os.path.join(CACHE_DIR, blob, cache_filename)
    blob_file = (blob + "/" + cache_filename).replace("\\", "/")

    try:
        is_exits = gcs.available and gcs.check_blob_exists(GCS_CACHE_BUCKET, blob_file)
    except Exception:
        is_exits = False

    if 'js_payload' not in st.session_state or st.session_state.get('replay_session_id') != cache_path:
        # 1. Try local file first
        if os.path.isfile(cache_path):
            with st.spinner("Loading Replay from local cache..."):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    st.session_state['js_payload'] = json.load(f)
                st.session_state['replay_session_id'] = cache_path
        # 2. Try GCS
        elif is_exits:
            gcs.download_one_file(GCS_CACHE_BUCKET, blob_file, cache_path)

            with st.spinner("Loading Replay package from GCS cache..."):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    st.session_state['js_payload'] = json.load(f)
                st.session_state['replay_session_id'] = cache_path
        # 3. Not cached anywhere
        else:
            st.info("Replay data is not cached yet. Generating it requires processing all telemetry points for 20 cars.")
            if st.button("Load & Generate Replay Data", type="primary"):
                generate_and_cache_replay_payload(session, max_lap_avail, cache_path, blob)
                st.rerun(scope="fragment")
            return

    if 'js_payload' in st.session_state:
        payload_json = json.dumps(st.session_state['js_payload'])
        
        template_path = os.path.join('components', 'ReplayEngine.html')
        
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
            
        html_code = html_template.replace('__PAYLOAD_JSON_PLACEHOLDER__', payload_json)
        components.html(html_code, height=1050, scrolling=True)