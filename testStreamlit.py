import streamlit as st
import fastf1
import fastf1.plotting
import pandas as pd
from datetime import datetime
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# --- CẤU HÌNH TRANG & CACHE ---
st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")
fastf1.Cache.enable_cache('f1_cache')
fastf1.plotting.setup_mpl(mpl_timedelta_support=False)

# Khởi tạo Session State để điều hướng trang
if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'home'
if 'selected_event' not in st.session_state:
    st.session_state['selected_event'] = None
if 'selected_year' not in st.session_state:
    st.session_state['selected_year'] = 2024

# --- TỪ ĐIỂN CỜ QUỐC GIA ---
FLAG_MAP = {
    "Bahrain": "🇧🇭", "Saudi Arabia": "🇸🇦", "Australia": "🇦🇺", "Japan": "🇯🇵", 
    "China": "🇨🇳", "USA": "🇺🇸", "United States": "🇺🇸", "Miami": "🇺🇸", 
    "Italy": "🇮🇹", "Monaco": "🇲🇨", "Spain": "🇪🇸", "Canada": "🇨🇦", 
    "Austria": "🇦🇹", "UK": "🇬🇧", "Great Britain": "🇬🇧", "Hungary": "🇭🇺", 
    "Belgium": "🇧🇪", "Netherlands": "🇳🇱", "Singapore": "🇸🇬", 
    "Azerbaijan": "🇦🇿", "Mexico": "🇲🇽", "Brazil": "🇧🇷", "Las Vegas": "🇺🇸", 
    "Qatar": "🇶🇦", "Abu Dhabi": "🇦🇪", "UAE": "🇦🇪"
}

def get_flag(country_name):
    return FLAG_MAP.get(country_name, "🏁")

# --- HÀM TẢI DỮ LIỆU ---
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
        st.error(f"Lỗi tải dữ liệu Session: {e}")
        return None

@st.cache_data(show_spinner=False)
def get_event_highlights(year, round_num):
    """Hàm tải trước thông tin Highlight (Winner, Pole, Fastest Lap) của chặng đua."""
    highlights = {"winner": "N/A", "pole": "N/A", "fastest_lap": "N/A"}
    try:
        # Lấy Winner & Fastest Lap từ phiên đua chính (R)
        race = fastf1.get_session(year, round_num, 'R')
        race.load(telemetry=False, weather=False, messages=False)
        
        if not race.results.empty:
            highlights["winner"] = race.results.iloc[0]['FullName']
            
            # Tìm Fastest Lap
            fastest_lap = race.laps.pick_fastest()
            if not pd.isnull(fastest_lap['LapTime']):
                driver = fastest_lap['Driver']
                time_str = str(fastest_lap['LapTime']).split()[-1][:9] # Cắt lấy hh:mm:ss.xxx
                highlights["fastest_lap"] = f"{driver} ({time_str})"

        # Lấy Pole Position từ phiên phân hạng (Q)
        qualy = fastf1.get_session(year, round_num, 'Q')
        qualy.load(telemetry=False, weather=False, messages=False)
        if not qualy.results.empty:
            highlights["pole"] = qualy.results.iloc[0]['FullName']
            
    except Exception as e:
        pass # Bỏ qua lỗi nếu chặng đua chưa diễn ra hoặc thiếu dữ liệu
    return highlights

# ==========================================
# GIAO DIỆN TRANG CHỦ (GRID LAYOUT)
# ==========================================
def render_home_page():
    st.title("🏎️ F1 Pulse - Race Calendar & Results")
    st.markdown("Khám phá lịch thi đấu, kết quả các chặng và phân tích chuyên sâu.")

    col_sel, _, _ = st.columns([1, 2, 2])
    with col_sel:
        # Giữ lại năm đã chọn nếu quay lại từ trang chi tiết
        selected_year = st.selectbox(
            "📅 Lựa chọn mùa giải:", 
            [2026, 2025, 2024, 2023, 2022, 2021], 
            index=[2026, 2025, 2024, 2023, 2022, 2021].index(st.session_state['selected_year'])
        )
        st.session_state['selected_year'] = selected_year

    st.divider()
    events_df = get_schedule(selected_year)

    if not events_df.empty:
        st.subheader(f"Lịch thi đấu & Kết quả mùa giải {selected_year}")
        
        for i in range(0, len(events_df), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(events_df):
                    event = events_df.iloc[i + j]
                    col = cols[j]
                    
                    round_num = event['RoundNumber']
                    event_name = event['EventName']
                    country = event['Country']
                    flag = get_flag(country)
                    
                    event_date = event['EventDate']
                    if pd.notna(event_date):
                        date_str = event_date.strftime("%d %b, %Y")
                        is_completed = event_date.tz_localize(None) < datetime.now()
                    else:
                        date_str = "TBA"; is_completed = False
                    
                    format_type = event.get('EventFormat', 'conventional').capitalize()
                    
                    with col:
                        with st.container(border=True):
                            st.markdown(f"#### {flag} Round {round_num}")
                            st.markdown(f"**{event_name}**")
                            st.caption(f"📍 {event['Location']}, {country} | 🗓️ {date_str}")
                            st.divider()
                            
                            if is_completed:
                                st.markdown("🟢 **Trạng thái:** Đã diễn ra")
                                winner = get_race_winner(selected_year, round_num)
                                st.markdown(f"🏆 **Winner:** {winner}")
                            else:
                                st.markdown("⏳ **Trạng thái:** Sắp tới")
                                if format_type in ['Sprint', 'Sprint_qualifying']:
                                    st.markdown("🏎️ **Format:** Sprint Weekend")
                                else:
                                    st.markdown("🏎️ **Format:** Conventional")
                            
                            # Xử lý sự kiện bấm nút: Lưu thông tin event và chuyển trang
                            if st.button(f"Phân tích chặng này", key=f"btn_{selected_year}_{round_num}", use_container_width=True, disabled=not is_completed):
                                st.session_state['selected_event'] = {
                                    'year': selected_year,
                                    'round': round_num,
                                    'name': event_name,
                                    'country': country
                                }
                                st.session_state['current_page'] = 'details'
                                st.rerun() # Tải lại trang ngay lập tức
    else:
        st.warning("Không tìm thấy dữ liệu lịch thi đấu cho mùa giải này.")


# ==========================================
# GIAO DIỆN TRANG CHI TIẾT (EVENT DETAILS)
# ==========================================
def render_details_page():
    event_info = st.session_state['selected_event']
    year = event_info['year']
    round_num = event_info['round']
    event_name = event_info['name']
    flag = get_flag(event_info['country'])

    # Nút Quay Lại
    if st.button("⬅️ Quay lại Danh sách chặng đua"):
        st.session_state['current_page'] = 'home'
        st.rerun()

    st.divider()

    # --- HEADER: TÊN CHẶNG & CHỌN SESSION ---
    col_title, col_session = st.columns([3, 1])
    
    with col_title:
        st.markdown(f"## {flag} {event_name} {year}")
    
    with col_session:
        # Lấy lịch trình của chặng này để điền vào Combo box Session
        schedule = fastf1.get_event_schedule(year)
        event_row = schedule[schedule['RoundNumber'] == round_num].iloc[0]
        
        # Tạo danh sách session dựa vào format (Sprint hay Thường)
        available_sessions = []
        format_type = event_row.get('EventFormat', 'conventional').lower()
        
        if format_type == 'sprint':
            available_sessions = ["Sprint", "Sprint Shootout", "Qualifying", "Race"]
            session_map = {"Sprint": "S", "Sprint Shootout": "SS", "Qualifying": "Q", "Race": "R"}
        elif format_type == 'sprint_qualifying': # Format mới từ 2024
            available_sessions = ["Sprint Qualifying", "Sprint", "Qualifying", "Race"]
            session_map = {"Sprint Qualifying": "SQ", "Sprint": "S", "Qualifying": "Q", "Race": "R"}
        else:
            available_sessions = ["FP1", "FP2", "FP3", "Qualifying", "Race"]
            session_map = {"FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "Qualifying": "Q", "Race": "R"}

        # Mặc định chọn Race (phiên cuối cùng)
        selected_session_name = st.selectbox("Chọn Phiên (Session):", available_sessions, index=len(available_sessions)-1, label_visibility="collapsed")
        session_code = session_map[selected_session_name]

    # --- 3 THẺ HIGHLIGHTS CHUẨN FORMULA 1 ---
    with st.spinner("Đang tải thông số nổi bật của chặng đua..."):
        highlights = get_event_highlights(year, round_num)
        
    col_win, col_pole, col_fast = st.columns(3)
    
    with col_win:
        with st.container(border=True):
            st.markdown("<p style='text-align: center; color: gray; margin-bottom: 0px;'>RACE WINNER</p>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center; margin-top: 0px;'>🏆 {highlights['winner']}</h3>", unsafe_allow_html=True)
            
    with col_pole:
        with st.container(border=True):
            st.markdown("<p style='text-align: center; color: gray; margin-bottom: 0px;'>POLE POSITION</p>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center; margin-top: 0px;'>⏱️ {highlights['pole']}</h3>", unsafe_allow_html=True)
            
    with col_fast:
        with st.container(border=True):
            st.markdown("<p style='text-align: center; color: gray; margin-bottom: 0px;'>FASTEST LAP</p>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center; margin-top: 0px;'>🚀 {highlights['fastest_lap']}</h3>", unsafe_allow_html=True)

    st.divider()

    # --- TẢI DỮ LIỆU CỦA SESSION ĐÃ CHỌN ---
    with st.spinner(f"Đang tải dữ liệu chi tiết cho phiên {selected_session_name}..."):
        session = load_f1_session(year, round_num, session_code)

    if session is not None:
        drivers = session.results['Abbreviation'].dropna().unique().tolist()

        # --- 6 TABS PHÂN TÍCH CHUYÊN SÂU ---
        tab_res, tab_pos, tab_strat, tab_laps, tab_dom, tab_tel = st.tabs([
            "📊 Results", 
            "📈 Positions", 
            "⏱️ Strategy", 
            "⏱️ Lap Times", 
            "🗺️ Track Dominance", 
            "📉 Telemetry"
        ])
        
        with tab_res:
            st.subheader(f"Kết quả phân hạng/đua - {selected_session_name}")
            
            res_df = session.results.copy()
            formatted_times = []
            
            # Lấy thời gian của người dẫn đầu (Winner) để kiểm tra
            winner_time = pd.NaT
            if not res_df.empty and pd.notna(res_df.iloc[0]['Time']):
                winner_time = res_df.iloc[0]['Time']
                
            for index, row in res_df.iterrows():
                pos = row['Position']
                time_val = row['Time']
                status = str(row['Status'])
                
                # NẾU LÀ PHIÊN PHÂN HẠNG (QUALIFYING)
                if session_code in ['Q', 'SQ']:
                    best_q = row.get('Q3', pd.NaT)
                    if pd.isna(best_q): best_q = row.get('Q2', pd.NaT)
                    if pd.isna(best_q): best_q = row.get('Q1', pd.NaT)
                    
                    if pd.notna(best_q):
                        q_sec = best_q.total_seconds()
                        minutes = int(q_sec // 60)
                        seconds = int(q_sec % 60)
                        # Format mm:ss không có thập phân
                        formatted_times.append(f"{minutes:02d}:{seconds:02d}")
                    else:
                        formatted_times.append(status)
                        
                # NẾU LÀ PHIÊN ĐUA CHÍNH (RACE / SPRINT)
                else:
                    if pd.isna(time_val):
                        # Bị bắt vòng hoặc Bỏ cuộc (Hiển thị Status)
                        formatted_times.append(status)
                    elif pos == 1 or pd.isna(winner_time):
                        # P1: Định dạng tổng thời gian hh:mm:ss
                        total_seconds = time_val.total_seconds()
                        hours = int(total_seconds // 3600)
                        minutes = int((total_seconds % 3600) // 60)
                        seconds = int(total_seconds % 60)
                        formatted_times.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                    else:
                        # P2 trở đi: time_val ĐÃ LÀ KHOẢNG CÁCH (Gap) trong FastF1
                        gap_seconds = time_val.total_seconds()
                        minutes = int(gap_seconds // 60)
                        seconds = int(gap_seconds % 60)
                        # Format +mm:ss không có thập phân
                        formatted_times.append(f"+{minutes:02d}:{seconds:02d}")
            
            # Xây dựng DataFrame cuối cùng
            display_df = pd.DataFrame({
                'Pos': res_df['Position'].astype(str).str.replace('.0', '', regex=False),
                'Driver': res_df['FullName'],
                'Team': res_df['TeamName'],
                'Grid': res_df['GridPosition'].astype(str).str.replace('.0', '', regex=False),
                'Status': res_df['Status'],
                'Time': formatted_times,
                'Point': res_df['Points'].astype(str).str.replace('.0', '', regex=False)
            })
            
            display_df = display_df.replace('nan', 'N/A')
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
        with tab_pos:
            # Tạo 3 tab con (Sub-tabs) bên trong tab Positions
            sub_chart, sub_rc, sub_analysis = st.tabs([
                "📈 Position Chart", 
                "🚨 Race Control", 
                "📊 Analysis"
            ])
            
            # -----------------------------------------
            # SUB-TAB 1: POSITION CHART (Lap-by-Lap)
            # -----------------------------------------
            with sub_chart:
                col_title, col_filter = st.columns([3, 1])
                with col_title:
                    st.subheader(f"Lap-by-Lap Position Changes - {selected_session_name}")
                    st.caption("Ghi chú: Trong cùng một đội, tay đua thứ hai sẽ được hiển thị bằng nét đứt (dashed line).")
                    
                with col_filter:
                    with st.expander("🔍 Lọc tay đua (Checkboxes)", expanded=False):
                        select_all = st.checkbox("Chọn tất cả", value=True, key="select_all_pos")
                        selected_drivers = []
                        for drv in drivers:
                            if st.checkbox(drv, value=select_all, key=f"check_{drv}"):
                                selected_drivers.append(drv)

                if not selected_drivers:
                    st.warning("👈 Vui lòng tick chọn ít nhất một tay đua.")
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
                            
                            if team_name not in team_count:
                                line_style = 'solid'
                                team_count[team_name] = 1
                            else:
                                line_style = 'dash'
                            
                            fig_pos.add_trace(go.Scatter(
                                x=drv_laps['LapNumber'],
                                y=drv_laps['Position'],
                                mode='lines+markers',
                                name=drv,
                                line=dict(color=color, width=3, dash=line_style),
                                marker=dict(size=4),
                                hovertemplate=f"<b>{drv}</b> ({team_name})<br>Lap: %{{x}}<br>Pos: P%{{y}}<extra></extra>"
                            ))

                    fig_pos.update_layout(
                        xaxis_title="Vòng (Lap)",
                        yaxis_title="Vị trí (Position)",
                        yaxis=dict(autorange="reversed", tickmode='linear', dtick=1),
                        hovermode="x unified",
                        height=550,
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_pos, use_container_width=True)

            # -----------------------------------------
            # SUB-TAB 2: RACE CONTROL (Timeline Messages)
            # -----------------------------------------
            with sub_rc:
                st.subheader(f"FIA Race Control Timeline - {selected_session_name}")
                rcm_df = session.race_control_messages
                
                if not rcm_df.empty:
                    rcm_display = rcm_df[['Time', 'Category', 'Flag', 'Message']].copy()
                    
                    # Định dạng lại cột Time (Timestamp) thành chuẩn hh:mm:ss cho dễ đọc
                    def format_rcm_time(ts):
                        if pd.isna(ts): return ""
                        # Gọi thẳng strftime vì ts là một đối tượng Timestamp của Pandas
                        return ts.strftime("%H:%M:%S")
                        
                    rcm_display['Time'] = rcm_display['Time'].apply(format_rcm_time)
                    st.dataframe(rcm_display, use_container_width=True, hide_index=True)
                else:
                    st.info("Không có dữ liệu hoặc thông báo từ Race Control cho phiên này.")

            # -----------------------------------------
            # SUB-TAB 3: ANALYSIS (Places Gained/Lost)
            # -----------------------------------------
            with sub_analysis:
                st.subheader("Places Gained/Lost Summary")
                res_df = session.results.copy()
                
                analysis_data = []
                for _, row in res_df.iterrows():
                    pos = pd.to_numeric(row['Position'], errors='coerce')
                    grid = pd.to_numeric(row['GridPosition'], errors='coerce')
                    
                    change_val = "N/A"
                    if pd.notna(pos) and pd.notna(grid) and grid > 0:
                        change_raw = int(grid) - int(pos)
                        if change_raw > 0:
                            change_val = f"↑ +{change_raw}"
                        elif change_raw < 0:
                            change_val = f"↓ {change_raw}"
                        else:
                            change_val = "- 0"
                    elif grid == 0:
                        change_val = "Pit Start" # Xử lý trường hợp xuất phát từ Pit Lane

                    analysis_data.append({
                        'Final Position': str(int(pos)) if pd.notna(pos) else "N/A",
                        'Driver': row['FullName'],
                        'Team': row['TeamName'],
                        'Grid': str(int(grid)) if pd.notna(grid) and grid > 0 else "Pit",
                        'Change': change_val,
                        'Status': row['Status']
                    })
                
                analysis_df = pd.DataFrame(analysis_data)
                
                # Hàm cấp màu sắc (CSS) cho Pandas Styler dựa trên giá trị text
                def style_change_col(val):
                    if isinstance(val, str):
                        if '↑' in val:
                            return 'color: #00cc66; font-weight: bold;' # Xanh lá
                        elif '↓' in val:
                            return 'color: #ff4b4b; font-weight: bold;' # Đỏ
                        elif '- 0' in val or 'Pit' in val or 'N/A' in val:
                            return 'color: gray;' # Xám
                    return ''

                # Áp dụng màu sắc vào dataframe (Tương thích với cả Pandas cũ và mới)
                try:
                    styled_df = analysis_df.style.map(style_change_col, subset=['Change'])
                except AttributeError:
                    styled_df = analysis_df.style.applymap(style_change_col, subset=['Change'])
                
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
        with tab_strat:
            # Tạo 2 sub-tabs cho phần Strategy
            sub_overview, sub_stint = st.tabs(["📊 Strategy Overview", "📋 Stint Detail Analysis"])
            
            # --- CHUẨN BỊ DỮ LIỆU LAPS CHUNG ---
            all_laps = session.laps.copy()
            # Loại bỏ các vòng không có thông tin Stint hoặc Compound hợp lệ
            all_laps = all_laps.dropna(subset=['Stint', 'Compound'])
            
            # Bảng màu chuẩn của Pirelli
            compound_colors = {
                'SOFT': '#FF3333',     # Đỏ
                'MEDIUM': '#FFF200',   # Vàng
                'HARD': '#FFFFFF',     # Trắng
                'INTERMEDIATE': '#39B54A', # Xanh lá
                'WET': '#00AEEF',      # Xanh dương
                'UNKNOWN': '#808080'   # Xám
            }

            # -----------------------------------------
            # SUB-TAB 1: STRATEGY OVERVIEW (Bar Chart)
            # -----------------------------------------
            with sub_overview:
                st.subheader(f"Tire Strategy & Stint Timeline - {selected_session_name}")
                st.markdown("Biểu đồ thể hiện chiến thuật sử dụng lốp của các tay đua. Được sắp xếp theo vị trí cán đích từ trên xuống dưới.")
                
                # Lấy danh sách tay đua theo thứ tự cán đích từ session.results
                finish_order = session.results['Abbreviation'].dropna().tolist()
                
                if finish_order and not all_laps.empty:
                    # Gom nhóm dữ liệu theo Driver, Stint, Compound để tính độ dài Stint
                    stints = all_laps.groupby(['Driver', 'Stint', 'Compound']).agg(
                        StartLap=('LapNumber', 'min'),
                        EndLap=('LapNumber', 'max'),
                        StintLength=('LapNumber', 'count')
                    ).reset_index()
                    
                    # Lọc chỉ lấy những tay đua có trong finish_order và ép kiểu sắp xếp
                    stints = stints[stints['Driver'].isin(finish_order)]
                    stints['Driver'] = pd.Categorical(stints['Driver'], categories=finish_order, ordered=True)
                    stints = stints.sort_values(['Driver', 'Stint'])
                    
                    # Dùng Plotly Express vẽ Bar chart nằm ngang (Gantt chart)
                    fig_strat = px.bar(
                        stints,
                        x='StintLength',
                        y='Driver',
                        color='Compound',
                        color_discrete_map=compound_colors,
                        orientation='h',
                        hover_data={
                            'StintLength': False, # Ẩn cột mặc định
                            'StartLap': True,
                            'EndLap': True,
                            'Stint': True,
                            'Laps': (stints['StintLength']) # Thêm nhãn Laps rõ ràng
                        },
                        labels={'Driver': 'Tay đua', 'StintLength': 'Số vòng (Laps)'}
                    )
                    
                    # Cập nhật giao diện: Viền đen cho các khối lốp, lật ngược trục Y
                    fig_strat.update_traces(marker_line_color='black', marker_line_width=1, opacity=0.9)
                    fig_strat.update_layout(
                        yaxis=dict(autorange="reversed", title=""),
                        xaxis=dict(title="Lap Number", showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                        height=max(500, len(finish_order) * 30), # Tự động giãn chiều cao theo số tay đua
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        legend_title_text="Compound"
                    )
                    st.plotly_chart(fig_strat, use_container_width=True)
                else:
                    st.info("Không đủ dữ liệu lốp để vẽ biểu đồ chiến thuật.")

            # -----------------------------------------
            # SUB-TAB 2: STINT DETAIL ANALYSIS (Data Table)
            # -----------------------------------------
            with sub_stint:
                st.subheader("Stint Performance Analysis")
                st.markdown("Phân tích chi tiết hiệu năng của từng bộ lốp.")
                
                # Hàm helper định dạng thời gian Lap (mm:ss.ms)
                def format_lap_time(td):
                    if pd.isna(td): return "N/A"
                    ts = td.total_seconds()
                    m = int(ts // 60)
                    s = ts % 60
                    return f"{m:02d}:{s:06.3f}"
                
                stint_stats = []
                
                # Duyệt qua từng Stint của từng tay đua
                for (driver, stint, compound), group in all_laps.groupby(['Driver', 'Stint', 'Compound']):
                    # 1. Tính chiều dài và thông tin cơ bản
                    length = len(group)
                    start_lap = int(group['LapNumber'].min())
                    end_lap = int(group['LapNumber'].max())
                    length_str = f"{length} (L{start_lap}-L{end_lap})"
                    
                    # 2. Lọc các vòng hợp lệ (bỏ qua In/Out laps ở Pit hoặc vòng ảo) để tính toán chính xác
                    valid_laps = group.dropna(subset=['LapTime'])
                    
                    fastest_str = "N/A"
                    avg_str = "N/A"
                    consist_str = "N/A"
                    deg_str = "N/A"
                    
                    if not valid_laps.empty:
                        # Thời gian nhanh nhất & Trung bình
                        fastest_str = format_lap_time(valid_laps['LapTime'].min())
                        avg_str = format_lap_time(valid_laps['LapTime'].mean())
                        
                        lap_seconds = valid_laps['LapTime'].dt.total_seconds()
                        
                        # --- TÍNH GIÁ TRỊ SIGMA (σ) CHO ĐỘ ỔN ĐỊNH ---
                        if len(lap_seconds) > 1:
                            # 1. Lọc nhiễu (Outliers): Bỏ qua các vòng dính cờ vàng, traffic hoặc lỗi nặng
                            # Ngưỡng chấp nhận: Không chậm hơn 5% so với vòng nhanh nhất của stint
                            threshold = valid_laps['LapTime'].min().total_seconds() * 1.05
                            clean_laps = lap_seconds[lap_seconds <= threshold]
                            
                            # 2. Tính Sigma (Population Standard Deviation với ddof=0)
                            if len(clean_laps) > 1:
                                sigma_val = clean_laps.std(ddof=0)
                            else:
                                # Fallback nếu stint quá ngắn (để tránh lỗi chia cho 0)
                                sigma_val = lap_seconds.std(ddof=0) 
                                
                            # Thay đổi text hiển thị thành ký hiệu σ
                            consist_str = f"σ = {sigma_val:.3f}s"
                        
                        # Độ mòn lốp (Degradation) - Dùng Numpy Polyfit để tìm độ dốc (Slope)
                        valid_deg = valid_laps.dropna(subset=['TyreLife'])
                        if len(valid_deg) > 2:
                            x = valid_deg['TyreLife'].astype(float)
                            y = valid_deg['LapTime'].dt.total_seconds()
                            try:
                                slope, _ = np.polyfit(x, y, 1) # Tìm hệ số góc bậc 1
                                # Nếu slope dương -> xe chậm đi (mòn lốp). Nếu âm -> xe nhanh lên do cạn xăng.
                                deg_str = f"{slope:+.3f} s/lap" 
                            except:
                                pass
                    
                    stint_stats.append({
                        'Driver': driver,
                        'Stint': int(stint),
                        'Compound': compound,
                        'Length': length_str,
                        'Fastest': fastest_str,
                        'Average': avg_str,
                        'Consist': consist_str,
                        'Degradation': deg_str
                    })
                
                if stint_stats:
                    df_stint_stats = pd.DataFrame(stint_stats)
                    # Sắp xếp theo tên tay đua (A-Z) và số Stint (1, 2, 3...)
                    df_stint_stats = df_stint_stats.sort_values(by=['Driver', 'Stint']).reset_index(drop=True)
                    
                    # Hàm đổi màu Compound trong bảng
                    def style_compound(val):
                        color_map = {
                            'SOFT': 'color: #FF3333; font-weight: bold;',
                            'MEDIUM': 'color: #FFF200; font-weight: bold;',
                            'HARD': 'color: white; font-weight: bold;',
                            'INTERMEDIATE': 'color: #39B54A; font-weight: bold;',
                            'WET': 'color: #00AEEF; font-weight: bold;'
                        }
                        return color_map.get(val, 'color: gray;')
                        
                    # Áp dụng màu cho cột Compound
                    try:
                        styled_stint_df = df_stint_stats.style.map(style_compound, subset=['Compound'])
                    except AttributeError:
                        styled_stint_df = df_stint_stats.style.applymap(style_compound, subset=['Compound'])

                    st.dataframe(styled_stint_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Không có dữ liệu chi tiết cho các Stint.")
            
        with tab_laps:
            # --- KHỞI TẠO STATE QUẢN LÝ ID DUY NHẤT CHO TỪNG COMBO BOX ---
            # Lưu danh sách các box đang hiển thị (mặc định 2 box đầu tiên)
            if 'lt_boxes' not in st.session_state:
                st.session_state['lt_boxes'] = ['box_0', 'box_1'] 
            # Bộ đếm để tạo ra ID không bao giờ trùng lặp khi Add thêm
            if 'lt_box_counter' not in st.session_state:
                st.session_state['lt_box_counter'] = 2

            # --- THIẾT KẾ GIAO DIỆN HEADER & CONTROLS ---
            col_title, col_controls = st.columns([1, 2.5])
            
            with col_title:
                st.subheader("Lap Time Comparison")
                st.caption(f"Phiên đua: {selected_session_name}")
                
            with col_controls:
                current_boxes = st.session_state['lt_boxes']
                n_boxes = len(current_boxes)
                
                # Chia cột: Mỗi ô box chiếm 1 phần, Nút Add chiếm 0.4 phần
                col_widths = [1] * n_boxes + [0.4]
                cols = st.columns(col_widths)
                
                selected_lt_drivers = []
                
                # Render các Combo Box lặp theo ID
                for i, box_id in enumerate(current_boxes):
                    with cols[i]:
                        default_idx = i if i < len(drivers) else 0
                        
                        # LOGIC UI: TỪ 3 BOX TRỞ LÊN SẼ XUẤT HIỆN NÚT ✖
                        if n_boxes >= 3:
                            # Chia cột con bên trong (Combo box chiếm 4 phần, Nút ✖ chiếm 1 phần)
                            sc1, sc2 = st.columns([4, 1])
                            with sc1:
                                drv = st.selectbox(
                                    f"Tay đua", 
                                    options=drivers, 
                                    index=default_idx,
                                    key=f"sel_{box_id}", # Dùng ID để Streamlit nhớ chính xác tay đua đã chọn
                                    label_visibility="collapsed"
                                )
                            with sc2:
                                # Nút ✖ xóa trực tiếp box ID này
                                if st.button("✖", key=f"del_{box_id}", help="Xóa tay đua này"):
                                    st.session_state['lt_boxes'].remove(box_id)
                                    st.rerun()
                        else:
                            # Dưới 3 box -> Ẩn nút ✖
                            drv = st.selectbox(
                                f"Tay đua", 
                                options=drivers, 
                                index=default_idx,
                                key=f"sel_{box_id}", 
                                label_visibility="collapsed"
                            )
                            
                        selected_lt_drivers.append(drv)
                
                # Render nút Add (Cột cuối cùng)
                with cols[-1]:
                    if st.button("➕ Add", disabled=n_boxes >= 6, use_container_width=True, help="Thêm tay đua để so sánh"):
                        # Tạo ID mới và nạp vào danh sách
                        new_id = f"box_{st.session_state['lt_box_counter']}"
                        st.session_state['lt_boxes'].append(new_id)
                        st.session_state['lt_box_counter'] += 1
                        st.rerun()

            st.divider()

            # --- VẼ ĐỒ THỊ LAP TIMES ---
            unique_drivers = list(dict.fromkeys(selected_lt_drivers))
            
            if unique_drivers:
                fig_laps = go.Figure()
                all_laps = session.laps
                
                for drv in unique_drivers:
                    drv_laps = all_laps.pick_drivers(drv).dropna(subset=['LapTime'])
                    
                    if not drv_laps.empty:
                        driver_info = session.get_driver(drv)
                        color = f"#{driver_info['TeamColor']}"
                        if color == "#nan" or not color: color = "white"
                        
                        lap_seconds = drv_laps['LapTime'].dt.total_seconds()
                        
                        formatted_times = drv_laps['LapTime'].apply(
                            lambda x: f"{int(x.total_seconds() // 60):02d}:{x.total_seconds() % 60:06.3f}"
                        )
                        
                        fig_laps.add_trace(go.Scatter(
                            x=drv_laps['LapNumber'],
                            y=lap_seconds,
                            mode='lines+markers',
                            name=drv,
                            # THÊM shape='spline' VÀO ĐÂY ĐỂ VUỐT MƯỢT ĐƯỜNG CONG
                            line=dict(color=color, width=2, shape='spline'), 
                            marker=dict(size=4),
                            customdata=formatted_times,
                            hovertemplate=f"<b>{drv}</b><br>Lap: %{{x}}<br>Time: %{{customdata}}<extra></extra>"
                        ))

                fig_laps.update_layout(
                    xaxis_title="Vòng đua (Lap Number)",
                    yaxis_title="Thời gian vòng (Seconds)",
                    hovermode="x unified",
                    height=600,
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                
                st.plotly_chart(fig_laps, use_container_width=True)
            else:
                st.warning("Vui lòng chọn ít nhất một tay đua.")
            
        with tab_dom:
            st.info("Tab Track Dominance (Bản đồ mini-sector) - Đang xây dựng")
            
        with tab_tel:
            st.info("Tab Telemetry (Phân tích chân ga, phanh, số) - Đang xây dựng")
            
    else:
        st.warning("Không thể tải dữ liệu cho phiên này.")


# ==========================================
# LUỒNG ĐIỀU KHIỂN CHÍNH (ROUTER)
# ==========================================
if st.session_state['current_page'] == 'home':
    render_home_page()
elif st.session_state['current_page'] == 'details':
    render_details_page()