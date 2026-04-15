import streamlit as st
import pandas as pd
import fastf1

# Import cấu hình và data loader
from core.config import get_flag_url
from core.data_loader import get_event_highlights, load_f1_session

# Import toàn bộ các components (Đã lưu ý import tab_position theo yêu cầu của bạn)
from components.tab_results import fragment_results
from components.tab_positions import fragment_positions
from components.tab_strategy import fragment_strategy
from components.tab_lap_times import fragment_lap_times
from components.tab_track_dominance import fragment_dominance
from components.tab_telemetry import render_telemetry_tab
from components.predictor_ui import render_predictor_tab
from components.replay_engine import fragment_replay_continuous

def render():
    if not st.session_state.get('selected_event'):
        st.warning("Please select a race from the Calendar first.")
        if st.button("Return to Calendar"):
            st.switch_page("pages/home.py")
        return

    event_info = st.session_state['selected_event']
    year = event_info['year']
    round_num = event_info['round']
    event_name = event_info['name']
    flag_url = get_flag_url(event_info['country'])

    st.divider()
    col_back, col_title, col_session = st.columns([0.15, 3.5, 1.2])

    # NÚT QUAY LẠI VÀ XÓA CACHE
    with col_back:
        st.write("") 
        if st.button("←", key="back_home_btn"):
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith(('ch_', 'sel_', 'del_', 'tel_', 'dom_')) or k in ['lt_boxes', 'lt_box_counter', 'sel_all_pos', 'replay_session_id', 'js_payload', 'predictions_race_id', 'predictions_df', 'gemini_insight', 'setup_profiler_fig']]
            for key in keys_to_clear:
                del st.session_state[key]
            st.switch_page("pages/home.py")

    with col_title:
        st.markdown(f"<h2 style='margin-top: 0;'><img src='{flag_url}' width='48' style='border-radius:6px; vertical-align:middle; margin-right:15px; box-shadow: 0 0 4px rgba(255,255,255,0.3);'> {event_name} {year}</h2>", unsafe_allow_html=True)
    
    # CHỌN PHIÊN ĐUA (SESSION)
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

    # --- TẢI VÀ HIỂN THỊ HIGHLIGHTS ---
    with st.spinner(f"Loading session details for {selected_session_name}..."):
        session = load_f1_session(year, round_num, session_code)

    if session is None:
        st.warning("Unable to load data for this session.")
        return

    drivers = session.results['Abbreviation'].dropna().unique().tolist()

    # PHÂN NHÁNH HIGHLIGHTS (PRACTICE VS RACE)
    if session_code.startswith('FP'):
        st.subheader(f"Session Highlights - {selected_session_name}")
        practice_top3 = session.results.nsmallest(3, 'BestLapTime')
        
        col_p1, col_p2, col_p3 = st.columns(3)
        p_cols = [col_p1, col_p2, col_p3]
        
        for i, (_, row) in enumerate(practice_top3.iterrows()):
            if i >= 3: break
            with p_cols[i]:
                with st.container(border=True):
                    t_val = row['BestLapTime']
                    if pd.notna(t_val):
                        ts = t_val.total_seconds()
                        time_str = f"{int(ts // 60)}:{ts % 60:06.3f}"
                    else:
                        time_str = "No Time"
                    
                    st.markdown(f"""
                        <div style='display: flex; justify-content: space-between;'>
                            <div>
                                <div style='color: #888; font-size: 0.85rem; font-weight: bold;'>P{i+1}</div>
                                <div style='font-size: 1.4rem; font-weight: bold;'>{row['FullName']}</div>
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

    # --- PHÂN NHÁNH GIAO DIỆN TABS ---
    if session_code.startswith('FP'):
        # TABS CHO PHIÊN THỬ NGHIỆM (PRACTICE)
        tab_res, tab_strat, tab_laps, tab_dom, tab_rc, tab_tel, tab_fake1, tab_fake2 = st.tabs([
            "📊 Results", "⏱️ Strategy", "⏱️ Lap Times", 
            "🗺️ Track Dominance", "🚨 Race Control", "📉 Telemetry", 
            "🧪 Setup Analysis (Beta)", "📈 Tyre Deg Predictor"
        ])
        
        with tab_res:
            fragment_results(session, session_code, selected_session_name)
        with tab_strat:
            fragment_strategy(session)
        with tab_laps: 
            fragment_lap_times(session, drivers)
        with tab_dom: 
            fragment_dominance(session, drivers)
        with tab_rc:
            st.subheader("Race Control Messages")
            rcm_df = session.race_control_messages
            if not rcm_df.empty:
                st.dataframe(rcm_df[['Time', 'Category', 'Message']], width='stretch', hide_index=True)
            else:
                st.info("No messages recorded.")
        with tab_tel:
            render_telemetry_tab(session, drivers)
        with tab_fake1:
            st.info("🚧 Tính năng 'Setup Analysis' đang được phát triển. Sắp tới tab này sẽ hiển thị so sánh High-Downforce vs Low-Drag setup dựa trên dữ liệu Speed Trap của phiên tập luyện.")
        with tab_fake2:
            st.info("🚧 Tính năng 'Tyre Deg Predictor' đang được phát triển. Tương lai sẽ sử dụng mô hình Machine Learning từ ml_core để dự đoán độ mòn lốp dựa trên long-run pace.")

    else:
        # TABS CHO PHIÊN ĐUA / PHÂN HẠNG (RACE / QUALIFYING)
        tab_res, tab_pos, tab_strat, tab_laps, tab_dom, tab_tel, tab_predict, tab_replay = st.tabs([
            "📊 Results", "📈 Positions", "⏱️ Strategy", "⏱️ Lap Times", 
            "🗺️ Track Dominance", "📉 Telemetry", "✨ Race Predictor", "🎥 Replay"
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

# Gọi hàm render khi file được chạy
render()