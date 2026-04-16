import streamlit as st
import pandas as pd
from datetime import datetime

from core.data_loader import get_schedule, get_race_winner
from core.config import get_flag_url

def render():
    st.markdown("""
        <style>
            /* ==============================================================
               1. ĐỒNG BỘ LAYOUT (Kéo Navbar sát lên mép trên giống Home)
               ============================================================== */
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            
            /* ==============================================================
               2. ĐỒNG BỘ NAVBAR (Nút đỏ, bo tròn, mảnh giống Home)
               ============================================================== */
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; 
                border: 1px solid #ff4b4b !important; 
                color: #ff4b4b !important;
                border-radius: 20px !important; 
                padding: 0px 15px !important; 
                font-size: 0.85rem !important;
                height: 32px !important; 
                min-height: 32px !important; 
                font-weight: bold !important;
                transition: all 0.2s ease-in-out !important;
            }
            [data-testid="stBaseButton-primary"]:hover { 
                background-color: rgba(255, 75, 75, 0.1) !important; 
                transform: translateY(-2px) !important;
            }

            /* ==============================================================
               3. CSS RIÊNG CHO NÚT BACK (Mũi tên xám, nhỏ gọn, an toàn 100%)
               Sử dụng class st-key tự động sinh ra từ key="btn_back_home"
               ============================================================== */
            div.st-key-btn_back_home {
                width: auto !important; /* Gỡ bỏ 100% width của thẻ cha nếu có */
            }
            div.st-key-btn_back_home button {
                background-color: transparent !important;
                border: 1px solid rgba(255, 255, 255, 0.2) !important;
                color: #a0a0a0 !important; /* Màu xám */
                border-radius: 50% !important; /* Biến thành hình tròn */
                height: 42px !important;
                width: 42px !important;
                min-height: 42px !important;
                padding: 0 !important;
                font-size: 1.2rem !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                margin-top: 0px !important; /* Đã reset margin để căn giữa bằng columns */
            }
            div.st-key-btn_back_home button:hover {
                background-color: rgba(255, 255, 255, 0.1) !important;
                border-color: #ffffff !important;
                color: #ffffff !important;
                transform: translateY(-2px) !important;
            }

            /* ==============================================================
               4. CSS CHO CÁC THẺ CHẶNG ĐUA (Secondary Buttons)
               Được phân lập hoàn toàn để không ảnh hưởng đến Navbar
               ============================================================== */
            div[data-testid="stButton"] { width: 100% !important; }
            
            [data-testid="stBaseButton-secondary"] {
                width: 100% !important; display: block !important; height: auto !important;
                padding: 1.2rem !important; border-radius: 12px !important;
                background-color: #16181c !important; border: 1px solid rgba(255, 255, 255, 0.1) !important;
                transition: all 0.2s ease-in-out !important;
            }
            [data-testid="stBaseButton-secondary"]:hover {
                border-color: #ff4b4b !important; background-color: #1e2025 !important;
                transform: translateY(-4px) !important; box-shadow: 0 8px 24px rgba(255, 75, 75, 0.15) !important;
            }
            [data-testid="stBaseButton-secondary"]:disabled {
                opacity: 0.7 !important; transform: none !important; box-shadow: none !important;
                border-color: rgba(255, 255, 255, 0.05) !important; cursor: not-allowed !important;
            }
            [data-testid="stBaseButton-secondary"] > div, [data-testid="stBaseButton-secondary"] div[data-testid="stMarkdownContainer"] {
                width: 100% !important; max-width: 100% !important; padding: 0 !important; margin: 0 !important; display: block !important;
            }
            [data-testid="stBaseButton-secondary"] p {
                display: grid !important; grid-template-columns: 45px minmax(0, 1fr) 95px !important;
                grid-template-rows: auto auto auto auto auto auto !important;
                grid-template-areas: "flag event round" "flag loc round" "divider divider divider" "date date status" "win1 win1 status" "win2 win2 status" !important;
                width: 100% !important; max-width: 100% !important; row-gap: 4px !important; column-gap: 8px !important; margin: 0 !important; text-align: left !important; align-items: center !important;
            }
            [data-testid="stBaseButton-secondary"] p img:nth-of-type(1) {
                grid-area: flag; width: 36px !important; height: 26px !important; border-radius: 4px !important; object-fit: cover !important; align-self: center !important; justify-self: start !important; box-shadow: 0 0 3px rgba(255,255,255,0.2) !important;
            }
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(1), [data-testid="stBaseButton-secondary"] p em:nth-of-type(1), [data-testid="stBaseButton-secondary"] p code:nth-of-type(1), [data-testid="stBaseButton-secondary"] p strong:nth-of-type(2), [data-testid="stBaseButton-secondary"] p em:nth-of-type(2) {
                justify-self: start !important; text-align: left !important; width: 100% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;
            }
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(1) { grid-area: event; font-size: 1.05rem !important; color: #ffffff !important; line-height: 1.2 !important; }
            [data-testid="stBaseButton-secondary"] p em:nth-of-type(1) { grid-area: loc; font-size: 0.85rem !important; color: #a0a0a0 !important; font-style: normal !important; }
            [data-testid="stBaseButton-secondary"] p code:nth-of-type(1) { grid-area: date; font-size: 0.85rem !important; color: #00cc66 !important; background: transparent !important; padding: 0 !important; font-family: inherit !important; font-weight: 600 !important; }
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(2) { grid-area: win1; font-size: 0.9rem !important; color: #e0e0e0 !important; margin-top: 4px !important; }
            [data-testid="stBaseButton-secondary"] p em:nth-of-type(2) { grid-area: win2; font-size: 0.85rem !important; color: #a0a0a0 !important; font-style: normal !important; }
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(1), [data-testid="stBaseButton-secondary"] p del:nth-of-type(2) {
                justify-self: end !important; text-align: center !important; text-decoration: none !important; font-weight: bold !important; color: #ffffff !important;
            }
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(1) { grid-area: round; font-size: 0.9rem !important; background-color: rgba(255, 255, 255, 0.1) !important; padding: 4px 10px !important; border-radius: 20px !important; }
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(2) { grid-area: status; font-size: 0.8rem !important; background: rgba(0,0,0,0.4) !important; padding: 4px 8px !important; border-radius: 6px !important; border: 1px solid rgba(255,255,255,0.1) !important; min-width: 80px !important; }
            [data-testid="stBaseButton-secondary"] p img:nth-of-type(2) { grid-area: divider; width: calc(100% + 2.4rem) !important; margin: 10px -1.2rem 8px -1.2rem !important; height: 1px !important; background-color: rgba(255,255,255,0.15) !important; }
        </style>
    """, unsafe_allow_html=True)

    # --- HEADER: Nút Back | Tiêu đề | Combo Box ---
    # THÊM THUỘC TÍNH: vertical_alignment="center" ĐỂ TẤT CẢ CÙNG CHỈNH GIỮA THEO CHIỀU DỌC
    col_back, col_title, col_sel = st.columns([0.15, 3.5, 1.2], vertical_alignment="center")
    
    with col_back:
        # Nút Back dùng type="primary" nhưng được bảo vệ bằng CSS .st-key-btn_back_home ở trên
        if st.button("←", key="btn_back_home", type="primary"):
            st.switch_page("pages/home.py")
            
    with col_title:
        # Xóa các margin thừa của thẻ H2
        st.markdown("<h2 style='margin: 0; padding: 0;'> Race Calendar & Results</h2>", unsafe_allow_html=True)
        
    with col_sel:
        if 'selected_year' not in st.session_state:
            st.session_state['selected_year'] = 2024
            
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 2
        
        # Combo Box 
        selected_year = st.selectbox("Season", years_list, index=safe_index, label_visibility="collapsed")
        st.session_state['selected_year'] = selected_year

    st.divider()
    events_df = get_schedule(selected_year)

    if not events_df.empty:
        div_img = "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
        for i in range(0, len(events_df), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(events_df):
                    event = events_df.iloc[i + j]
                    col = cols[j]
                    
                    round_num = event['RoundNumber']
                    country = str(event['Country'])
                    flag_url = get_flag_url(country)
                    event_name = str(event['EventName']).strip().replace('_', '').replace('*', '').replace('~', '').replace('`', '')
                    location = str(event.get('Location', country)).strip().replace('_', '').replace('*', '').replace('~', '').replace('`', '')
                    
                    now = datetime.now()
                    event_date = event['EventDate'].tz_localize(None) if pd.notna(event['EventDate']) else None
                    date_str = "🗓️ " + event_date.strftime("%d %b, %Y") if event_date else "TBA"
                    
                    format_type = str(event.get('EventFormat', 'conventional')).capitalize().replace('_', ' ')
                    if not format_type: format_type = "Conventional"
                    elif format_type in ['Sprint', 'Sprint qualifying'] : format_type = "Sprint Weekend"
                    
                    status_text = "⏳ Upcoming"
                    is_completed = False
                    
                    if event_date:
                        time_diff = (now - event_date).total_seconds()
                        if time_diff > 10800:
                            status_text = "🟢 Completed"
                            is_completed = True
                            winner_info = get_race_winner(selected_year, round_num)
                            if winner_info == "N/A":
                                status_text = "❌ Cancelled"
                                is_completed = False
                                line1 = "Format: " + format_type 
                            elif "(" in winner_info:
                                w_name, w_team = winner_info.split(" (")
                                line1 = f"🏆 {w_name.strip()}"
                                line2 = f"👥 {w_team.replace(')', '').strip()}"
                            else:
                                line1 = f"🏆 {winner_info}"; line2 = "🏎️ N/A"
                        elif time_diff > 0:
                            status_text = "🔥 Ongoing"; line1 = "Format: " + format_type
                        else:
                            line1 = "Format: " + format_type
                    else:
                        line1 = "Format: "
                            
                    current_flag = flag_url if flag_url else div_img
                    if status_text == "⏳ Upcoming":
                        btn_label = f"![f]({current_flag})__{event_name}__*{location}*~Round {round_num}~![d]({div_img})``{date_str}``__{line1}__~{status_text}~"
                    else:
                        btn_label = f"![f]({current_flag})__{event_name}__*{location}*~Round {round_num}~![d]({div_img})``{date_str}``__{line1}__*{line2}*~{status_text}~"
                    
                    with col:
                        # Sử dụng button mặc định (Secondary) để giữ đúng giao diện thẻ chặng đua
                        if st.button(btn_label, key=f"btn_ra_{selected_year}_{round_num}", use_container_width=True, disabled=not is_completed):
                            st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                            st.switch_page("pages/details.py")
    else:
        st.warning("No schedule data found for this season.")

render()