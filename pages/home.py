import streamlit as st
import pandas as pd
from datetime import datetime

from core.data_loader import get_schedule, get_race_winner
from core.config import get_flag_url

# Link ảnh nền mẫu cho các chặng đua (Bạn có thể thay bằng ảnh thật sau)
TRACK_BGS = {
    "Bahrain": "https://images.unsplash.com/photo-1541344999736-83eca272f6fc?q=80&w=800&auto=format&fit=crop",
    "Saudi Arabia": "https://images.unsplash.com/photo-1580273916550-e323be2ae537?q=80&w=800&auto=format&fit=crop",
    "Australia": "https://images.unsplash.com/photo-1514316454349-750a7fd3da3a?q=80&w=800&auto=format&fit=crop",
    "Japan": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?q=80&w=800&auto=format&fit=crop",
    "China": "https://images.unsplash.com/photo-1508804185872-d7badad00f7d?q=80&w=800&auto=format&fit=crop",
    "Default": "https://images.unsplash.com/photo-1532938914619-3549ea5b3406?q=80&w=800&auto=format&fit=crop"
}

def render():
    st.markdown("""
        <style>
            /* Reset khoảng cách của Streamlit */
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            
            /* --- CSS Tiêu đề mục --- */
            .sec-header { display: flex; justify-content: space-between; align-items: flex-end; margin-top: 10px; margin-bottom: 15px; }
            .sec-title { color: #ffffff; font-size: 1.15rem; font-weight: 700; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;}
            .sec-title span { color: #ff4b4b; }
            
            /* --- CSS BẢNG XẾP HẠNG (STANDINGS CARD) --- */
            .st-card {
                background-color: #16181c; border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px; padding: 18px 20px; display: flex; justify-content: space-between;
                align-items: center; margin-bottom: 15px; transition: transform 0.2s;
            }
            .st-card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.1); }
            .st-info { display: flex; flex-direction: column; }
            .st-name { color: #a0a0a0; font-size: 0.9rem; margin-bottom: 4px; font-weight: bold;}
            .st-pts { color: #ffffff; font-size: 1.4rem; font-weight: 900; }
            .st-trend { color: #00cc66; font-size: 0.8rem; margin-top: 2px; font-weight: bold;}
            .st-logo { font-size: 1.8rem; opacity: 0.8; }

            /* --- CSS THẺ CHẶNG ĐUA (Chỉ áp dụng cho nút Secondary mặc định) --- */
            [data-testid="stBaseButton-secondary"] {
                width: 100% !important; display: block !important; height: 125px !important;
                padding: 0 !important; border-radius: 12px !important; background-color: #000000 !important;
                border: 1px solid rgba(255, 255, 255, 0.1) !important; position: relative !important; overflow: hidden !important;
                transition: transform 0.2s, border-color 0.2s !important; margin-bottom: 12px !important;
            }
            [data-testid="stBaseButton-secondary"]:hover { border-color: #ff4b4b !important; transform: scale(1.02) !important; box-shadow: 0 4px 15px rgba(255,75,75,0.2) !important;}
            [data-testid="stBaseButton-secondary"]:disabled { opacity: 0.7; filter: grayscale(70%); cursor: not-allowed !important; transform: none !important; }
            
            [data-testid="stBaseButton-secondary"] > div, [data-testid="stBaseButton-secondary"] div[data-testid="stMarkdownContainer"] {
                width: 100% !important; height: 100% !important; padding: 0 !important; margin: 0 !important; display: block !important;
            }
            
            /* Flex layout đè lên ảnh */
            [data-testid="stBaseButton-secondary"] p {
                display: flex !important; flex-direction: column !important; justify-content: center !important;
                width: 100% !important; height: 100% !important; margin: 0 !important; padding: 15px 20px !important;
                position: relative !important; z-index: 2 !important; text-align: left !important; align-items: flex-start !important;
            }

            /* Ảnh 1: Hình nền mờ che phủ toàn nút */
            [data-testid="stBaseButton-secondary"] p img:nth-of-type(1) {
                position: absolute !important; top: 0 !important; left: 0 !important;
                width: 100% !important; height: 100% !important; object-fit: cover !important;
                opacity: 0.3 !important; z-index: -1 !important;
            }
            /* Ảnh 2: Cờ quốc gia ở góc phải */
            [data-testid="stBaseButton-secondary"] p img:nth-of-type(2) {
                position: absolute !important; right: 20px !important; top: 20px !important;
                width: 26px !important; border-radius: 4px !important; opacity: 0.9 !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.5) !important;
            }

            /* Chữ trong thẻ chặng đua */
            [data-testid="stBaseButton-secondary"] p strong { font-size: 1.15rem !important; color: #ffffff !important; margin-bottom: 2px !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }
            [data-testid="stBaseButton-secondary"] p em { font-size: 0.85rem !important; color: #d0d0d0 !important; font-style: normal !important; margin-bottom: 8px !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }
            [data-testid="stBaseButton-secondary"] p code { font-size: 0.85rem !important; background: rgba(0,0,0,0.6) !important; padding: 4px 10px !important; border-radius: 4px !important; font-weight: bold !important; font-family: inherit !important; border: 1px solid rgba(255,255,255,0.1); }
            
            /* --- CSS Nút "View All RACES" (Primary Button) --- */
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; border: 1px solid #ff4b4b !important; color: #ff4b4b !important;
                border-radius: 20px !important; padding: 0px 15px !important; font-size: 0.85rem !important;
                height: 32px !important; min-height: 32px !important; font-weight: bold !important;
            }
            [data-testid="stBaseButton-primary"]:hover { background-color: rgba(255, 75, 75, 0.1) !important; }
        </style>
    """, unsafe_allow_html=True)

    # --- PHẦN HEADER ---
    col_hdr1, col_hdr2 = st.columns([4, 1])
    with col_hdr1:
        st.markdown("<h1 style='margin-bottom: 0; padding-bottom: 0;'>Dashboard</h1>", unsafe_allow_html=True)
        if 'selected_year' not in st.session_state: st.session_state['selected_year'] = 2026
        st.markdown(f"<p style='color: #888; font-size: 0.95rem; font-weight: bold;'>Season Overview {st.session_state['selected_year']}</p>", unsafe_allow_html=True)
    
    with col_hdr2:
        st.markdown("<br>", unsafe_allow_html=True)
        years_list = [2026, 2025, 2024, 2023, 2022, 2021]
        selected_year = st.selectbox("Season", years_list, index=years_list.index(st.session_state['selected_year']), label_visibility="collapsed")
        st.session_state['selected_year'] = selected_year

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # --- CHIA LAYOUT CỘT CHÍNH: Tỷ lệ 6.5 vs 3.5 ---
    col_left, col_right = st.columns([6.5, 3.5], gap="large")

    # ==========================================
    # CỘT TRÁI: TEAM & DRIVER STANDINGS
    # ==========================================
    with col_left:
        # Dữ liệu tĩnh (Dummy data) dựng theo ảnh UI mẫu
        teams_data = [
            {"name": "Mercedes", "pts": "135", "trend": "↑ 37", "icon": "⚝", "color": "#00D2BE"},
            {"name": "Ferrari", "pts": "90", "trend": "↑ 23", "icon": "🐎", "color": "#DC0000"},
            {"name": "McLaren", "pts": "46", "trend": "↑ 26", "icon": "⚡", "color": "#FF8700"},
            {"name": "Haas F1 Team", "pts": "18", "trend": "↑ 1", "icon": "H", "color": "#FFFFFF"}
        ]
        drivers_data = [
            {"name": "Kimi Antonelli", "pts": "72", "trend": "↑ 25", "icon": "👤", "color": "#00D2BE"},
            {"name": "George Russell", "pts": "63", "trend": "↑ 12", "icon": "👤", "color": "#00D2BE"},
            {"name": "Charles Leclerc", "pts": "49", "trend": "↑ 15", "icon": "👤", "color": "#DC0000"},
            {"name": "Lewis Hamilton", "pts": "41", "trend": "↑ 8", "icon": "👤", "color": "#DC0000"}
        ]

        # 1. TEAM STANDINGS
        st.markdown("<div class='sec-header'><div class='sec-title'>Team <span>Standings</span></div></div>", unsafe_allow_html=True)
        for i in range(0, len(teams_data), 2):
            c1, c2 = st.columns(2)
            with c1:
                t1 = teams_data[i]
                st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{t1['name']}</div><div class='st-pts'>{t1['pts']} PTS</div><div class='st-trend'>{t1['trend']}</div></div><div class='st-logo' style='color:{t1['color']};'>{t1['icon']}</div></div>", unsafe_allow_html=True)
            with c2:
                if i+1 < len(teams_data):
                    t2 = teams_data[i+1]
                    st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{t2['name']}</div><div class='st-pts'>{t2['pts']} PTS</div><div class='st-trend'>{t2['trend']}</div></div><div class='st-logo' style='color:{t2['color']};'>{t2['icon']}</div></div>", unsafe_allow_html=True)

        # 2. DRIVER STANDINGS
        st.markdown("<div class='sec-header' style='margin-top: 25px;'><div class='sec-title'>Driver <span>Standings</span></div></div>", unsafe_allow_html=True)
        for i in range(0, len(drivers_data), 2):
            c1, c2 = st.columns(2)
            with c1:
                d1 = drivers_data[i]
                st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{d1['name']}</div><div class='st-pts'>{d1['pts']} PTS</div><div class='st-trend'>{d1['trend']}</div></div><div class='st-logo' style='color:{d1['color']};'>{d1['icon']}</div></div>", unsafe_allow_html=True)
            with c2:
                if i+1 < len(drivers_data):
                    d2 = drivers_data[i+1]
                    st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{d2['name']}</div><div class='st-pts'>{d2['pts']} PTS</div><div class='st-trend'>{d2['trend']}</div></div><div class='st-logo' style='color:{d2['color']};'>{d2['icon']}</div></div>", unsafe_allow_html=True)

    # ==========================================
    # CỘT PHẢI: RACE ANALYTICS (Tóm tắt chặng đua)
    # ==========================================
    with col_right:
        c_title, c_link = st.columns([1.5, 1])
        with c_title: 
            st.markdown("<div class='sec-header'><div class='sec-title'>Race <span>Analytics</span></div></div>", unsafe_allow_html=True)
        with c_link:
            st.write("") 
            # Sử dụng type="primary" để có giao diện nút viền đỏ "View All"
            if st.button("View All →", type="primary", use_container_width=True):
                st.switch_page("pages/race_analytics.py")

        events_df = get_schedule(selected_year)
        if not events_df.empty:
            # Chỉ lấy 4 chặng đua (VD: 2 chặng vừa qua, 2 chặng sắp tới) để hiển thị cho gọn
            for _, event in events_df.head(4).iterrows():
                round_num = event['RoundNumber']
                event_name = str(event['EventName']).strip()
                country = str(event['Country'])
                
                flag_url = get_flag_url(country)
                bg_url = TRACK_BGS.get(country, TRACK_BGS["Default"])
                
                event_date = event['EventDate'].tz_localize(None) if pd.notna(event['EventDate']) else None
                date_str = event_date.strftime("%d %b, %Y") if event_date else "TBA"
                
                now = datetime.now()
                is_completed = False
                status_code = ""
                
                if event_date:
                    time_diff = (now - event_date).total_seconds()
                    if time_diff > 10800:
                        is_completed = True
                        winner = get_race_winner(selected_year, round_num)
                        if winner == "N/A":
                            status_code = "<code style='color:#ff4b4b;'>CANCELLED</code>"
                            is_completed = False
                        else:
                            winner_name = winner.split(" (")[0] if "(" in winner else winner
                            status_code = f"<code style='color:#00cc66;'>Winner: {winner_name}</code>"
                    elif time_diff > 0:
                        status_code = "<code style='color:#ffaa00;'>LIVE NOW</code>"
                    else:
                        status_code = "<code style='color:#ffffff;'>UPCOMING</code>"
                else:
                    status_code = "<code style='color:#ffffff;'>TBA</code>"

                # Cấu trúc: Ảnh Nền -> Ảnh Cờ -> Tên Chặng -> Địa điểm -> Trạng thái
                btn_label = f"![bg]({bg_url})\n![f]({flag_url})\n__{event_name}__\n*{date_str} - {country}*\n{status_code}"

                # Render nút bấm (Sẽ tự động nhận CSS của stBaseButton-secondary)
                if st.button(btn_label, key=f"btn_dash_{selected_year}_{round_num}", disabled=not is_completed):
                    st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                    st.switch_page("pages/details.py")
        else:
            st.warning("No races found.")

render()