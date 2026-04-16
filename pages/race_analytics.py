import streamlit as st
import pandas as pd
from datetime import datetime

from core.data_loader import get_schedule, get_race_winner
from core.config import get_flag_url

def render():
    st.markdown("""
        <style>
            [data-testid="stButton"] button {
                width: 100% !important;        /* QUAN TRỌNG: Ép nút bấm tràn 100% cột */
                display: block !important;     /* QUAN TRỌNG: Bỏ inline-flex mặc định của Streamlit */
                height: auto !important;
                padding: 1rem !important;
                border-radius: 12px !important;
                background-color: #16181c !important;
                border: 1px solid rgba(255, 255, 255, 0.1) !important;
                transition: all 0.2s ease-in-out !important;
            }
            [data-testid="stButton"] button:hover {
                border-color: #ff4b4b !important;
                background-color: #1e2025 !important;
                transform: translateY(-4px) !important;
                box-shadow: 0 8px 24px rgba(255, 75, 75, 0.15) !important;
            }
            [data-testid="stButton"] button:disabled {
                opacity: 0.7 !important;
                transform: none !important;
                box-shadow: none !important;
                border-color: rgba(255, 255, 255, 0.05) !important;
                cursor: not-allowed !important;
            }
            
            /* XÓA PADDING ẨN CỦA STREAMLIT: Ép các div bọc nội dung phải chiếm 100% chiều rộng */
            [data-testid="stButton"] button > div, 
            [data-testid="stButton"] button div[data-testid="stMarkdownContainer"] {
                width: 100% !important;
                max-width: 100% !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            
            /* Định nghĩa Lưới 2 nửa, 3 cột, nhiều dòng */
            [data-testid="stButton"] button p {
                display: grid !important;
                grid-template-columns: 48px 1fr auto !important;
                grid-template-rows: auto auto auto auto auto auto !important;
                grid-template-areas:
                    "flag event round"
                    "flag loc round"
                    "divider divider divider"
                    "date date status"
                    "win1 win1 status"
                    "win2 win2 status" !important;
                width: 100% !important;
                max-width: 100% !important;
                row-gap: 4px !important;
                column-gap: 8px !important;
                margin: 0 !important;
                text-align: left !important;
                align-items: center !important;
            }
            
            /* 1. Flag (Cột trái nửa trên, chiếm 2 dòng) */
            [data-testid="stButton"] button p img:nth-of-type(1) {
                grid-area: flag;
                width: 36px !important;
                height: 26px !important;
                border-radius: 4px !important;
                object-fit: cover !important;
                align-self: center !important;
                justify-self: start !important; /* Căn trái */
                box-shadow: 0 0 3px rgba(255,255,255,0.2) !important;
            }
            /* 2. Event Name (Giữa dòng 1) */
            [data-testid="stButton"] button p strong:nth-of-type(1) {
                grid-area: event;
                font-size: 1.05rem !important;
                color: #ffffff !important;
                line-height: 1.2 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                justify-self: start !important; /* Căn trái */
            }
            /* 3. Location (Giữa dòng 2) */
            [data-testid="stButton"] button p em:nth-of-type(1) {
                grid-area: loc;
                font-size: 0.85rem !important;
                color: #a0a0a0 !important;
                font-style: normal !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                justify-self: start !important; /* Căn trái */
            }
            /* 4. Round Number (Phải nửa trên, chiếm 2 dòng) */
            [data-testid="stButton"] button p del:nth-of-type(1) {
                grid-area: round;
                font-size: 0.9rem !important;
                color: #ffffff !important;
                background-color: rgba(255, 255, 255, 0.1) !important;
                padding: 4px 10px !important;
                border-radius: 20px !important;
                text-decoration: none !important;
                font-weight: bold !important;
                align-self: center !important;
                justify-self: end !important; /* Căn phải */
            }
            /* 5. Divider (Đường kẻ ngang) - Dùng negative margin để kéo dài mép tới mép thẻ */
            [data-testid="stButton"] button p img:nth-of-type(2) {
                grid-area: divider;
                width: calc(100% + 2rem) !important;
                margin: 10px -1rem 8px -1rem !important;
                height: 1px !important;
                background-color: rgba(255,255,255,0.15) !important;
            }
            /* 6. Date (Trái dòng 1 nửa dưới) */
            [data-testid="stButton"] button p code:nth-of-type(1) {
                grid-area: date;
                font-size: 0.85rem !important;
                color: #00cc66 !important;
                background: transparent !important;
                padding: 0 !important;
                font-family: inherit !important;
                font-weight: 600 !important;
                justify-self: start !important; /* Căn trái */
            }
            /* 7. Winner Name / Format Line 1 (Trái dòng 2 nửa dưới) */
            [data-testid="stButton"] button p strong:nth-of-type(2) {
                grid-area: win1;
                font-size: 0.9rem !important;
                color: #e0e0e0 !important;
                margin-top: 4px !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                justify-self: start !important; /* Căn trái */
            }
            /* 8. Winner Team / Format Line 2 (Trái dòng 3 nửa dưới) */
            [data-testid="stButton"] button p em:nth-of-type(2) {
                grid-area: win2;
                font-size: 0.85rem !important;
                color: #a0a0a0 !important;
                font-style: normal !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                justify-self: start !important; /* Căn trái */
            }
            /* 9. Status (Phải nửa dưới, chiếm 3 dòng) */
            [data-testid="stButton"] button p del:nth-of-type(2) {
                grid-area: status;
                font-size: 0.8rem !important;
                color: #ffffff !important;
                text-decoration: none !important;
                font-weight: bold !important;
                align-self: start !important;
                justify-self: end !important; /* Căn phải */
                background: rgba(0,0,0,0.4) !important;
                padding: 4px 8px !important;
                border-radius: 6px !important;
                border: 1px solid rgba(255,255,255,0.1) !important;
            }
        </style>
    """, unsafe_allow_html=True)

    if st.button("← Back to Dashboard", key="btn_back_home"):
        st.switch_page("pages/home.py")

    col_title, col_sel = st.columns([3, 1])
    with col_title:
        st.title("🏎️ F1 Pulse")
        st.markdown("Explore race schedules, results, and in-depth performance analysis.")
        
    with col_sel:
        st.markdown("<br>", unsafe_allow_html=True)
        if 'selected_year' not in st.session_state:
            st.session_state['selected_year'] = 2026
            
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        selected_year = st.selectbox("📅 Select Season:", years_list, index=years_list.index(st.session_state['selected_year']), label_visibility="collapsed")
        st.session_state['selected_year'] = selected_year

    st.divider()
    events_df = get_schedule(selected_year)

    if not events_df.empty:
        st.subheader(f"Race Calendar & Results - Season {selected_year}")
        
        div_img = "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
        
        # Vẽ lưới các thẻ sự kiện
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
                    
                    # Xác định trạng thái
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
                                line1 = f"🏆 {winner_info}"
                                line2 = "🏎️ N/A"
                                
                        elif time_diff > 0: # Nằm trong khoảng 3 tiếng từ lúc xuất phát
                            status_text = "🔥 Ongoing"
                            line1 = "Format: " + format_type
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
                        if st.button(btn_label, key=f"btn_{selected_year}_{round_num}", use_container_width=True, disabled=not is_completed):
                            st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                            st.switch_page("pages/details.py")
    else:
        st.warning("No schedule data found for this season.")

render()