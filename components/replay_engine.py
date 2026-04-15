import streamlit as st
import pandas as pd
import json
import os
import time
import streamlit.components.v1 as components

CACHE_DIR = '../f1_cache'

# ==========================================
# LAZY-LOADED REPLAY ENGINE (NATIVE JS)
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
        
        # Track Geometry
        ref_lap = session.laps.pick_fastest()
        ref_tel = ref_lap.get_telemetry()
        payload["track_path"] = ref_tel[['X', 'Y']].dropna().values.tolist()
        payload["min_x"], payload["max_x"] = float(ref_tel['X'].min()), float(ref_tel['X'].max())
        payload["min_y"], payload["max_y"] = float(ref_tel['Y'].min()), float(ref_tel['Y'].max())
        
        # Finish Line Position
        payload["finish_line"] = [float(ref_tel['X'].iloc[0]), float(ref_tel['Y'].iloc[0])]
        
        # Start Line Position
        try:
            lap1 = session.laps[session.laps['LapNumber'] == 1].iloc[0]
            lap1_tel = lap1.get_telemetry()
            payload["start_line"] = [float(lap1_tel['X'].iloc[0]), float(lap1_tel['Y'].iloc[0])]
        except: pass

        # Corners Vector
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
        
        template_path = os.path.join('components', 'ReplayEngine.html')
        
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
            
        html_code = html_template.replace('__PAYLOAD_JSON_PLACEHOLDER__', payload_json)
        components.html(html_code, height=1050, scrolling=True)