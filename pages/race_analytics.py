import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import os

from core.data_loader import get_schedule, get_race_winner
from core.config import get_flag_url

# ==========================================
# 1. THÊM DICTIONARY VÀ HÀM XỬ LÝ ẢNH TỪ HOME
# ==========================================
TRACK_BGS = {
    "Bahrain Grand Prix": "assets/BGS/Bahrain Grand Prix.avif",
    "Saudi Arabian Grand Prix": "assets/BGS/Saudi Arabian Grand Prix.avif",
    "Australian Grand Prix": "assets/BGS/Australian Grand Prix.avif",
    "Japanese Grand Prix": "assets/BGS/Japanese Grand Prix.avif",
    "Chinese Grand Prix": "assets/BGS/Chinese Grand Prix.avif",
    "Miami Grand Prix": "assets/BGS/Miami Grand Prix.avif",
    "Canadian Grand Prix": "assets/BGS/Canadian Grand Prix.avif",
    "Monaco Grand Prix": "assets/BGS/Monaco Grand Prix.avif",
    "Barcelona Grand Prix": "assets/BGS/Barcelona Grand Prix.avif",
    "Austrian Grand Prix": "assets/BGS/Austrian Grand Prix.avif",
    "British Grand Prix": "assets/BGS/British Grand Prix.avif",
    "Belgian Grand Prix": "assets/BGS/Belgian Grand Prix.avif",
    "Hungarian Grand Prix": "assets/BGS/Hungarian Grand Prix.avif",
    "Dutch Grand Prix": "assets/BGS/Dutch Grand Prix.avif",
    "Italian Grand Prix": "assets/BGS/Italian Grand Prix.avif",
    "Spanish Grand Prix": "assets/BGS/Spanish Grand Prix.avif",
    "Azerbaijan Grand Prix": "assets/BGS/Azerbaijan Grand Prix.avif",
    "Singapore Grand Prix": "assets/BGS/Singapore Grand Prix.avif",
    "United States Grand Prix": "assets/BGS/United States Grand Prix.avif",
    "Mexico City Grand Prix": "assets/BGS/Mexico City Grand Prix.avif",
    "São Paulo Grand Prix": "assets/BGS/Sao Paulo Grand Prix.avif",
    "Las Vegas Grand Prix": "assets/BGS/Las Vegas Grand Prix.avif",
    "Qatar Grand Prix": "assets/BGS/Qatar Grand Prix.avif",
    "Abu Dhabi Grand Prix": "assets/BGS/Abu Dhabi Grand Prix.avif",
    "Saudi Arabia Grand Prix": "assets/BGS/Saudi Arabia Grand Prix.avif",
    "Default": "https://images.unsplash.com/photo-1532938914619-3549ea5b3406?q=80&w=800&auto=format&fit=crop"
}

@st.cache_data(show_spinner=False)
def get_image_base64(path):
    if path and isinstance(path, str) and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = path.split('.')[-1].lower()
            mime_types = {"avif": "image/avif", "png": "image/png", "jpg": "image/jpeg"}
            mime = mime_types.get(ext, "image/jpeg")
            return f"data:{mime};base64,{b64}"
    return None

def load_bg_image(path_or_url):
    if not path_or_url:
        return TRACK_BGS.get("Default", "")
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return get_image_base64(path_or_url) or TRACK_BGS.get("Default", "")

# ==========================================
# 2. RENDER GIAO DIỆN CHÍNH
# ==========================================
def render():
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; border: 1px solid #ff4b4b !important; color: #ff4b4b !important;
                border-radius: 20px !important; padding: 0px 15px !important; font-size: 0.85rem !important; 
                height: 32px !important; min-height: 32px !important; font-weight: bold !important; transition: all 0.2s ease-in-out !important;
            }
            [data-testid="stBaseButton-primary"]:hover { background-color: rgba(255, 75, 75, 0.1) !important; transform: translateY(-2px) !important; }

            div.st-key-btn_back_home { width: auto !important; }
            div.st-key-btn_back_home button {
                background-color: transparent !important; border: 1px solid rgba(255, 255, 255, 0.2) !important;
                color: #a0a0a0 !important; border-radius: 50% !important; height: 42px !important; width: 42px !important;
                min-height: 42px !important; padding: 0 !important; font-size: 1.2rem !important; display: flex !important; align-items: center !important; justify-content: center !important; margin-top: 0px !important; 
            }
            div.st-key-btn_back_home button:hover { background-color: rgba(255, 255, 255, 0.1) !important; border-color: #ffffff !important; color: #ffffff !important; transform: translateY(-2px) !important; }

            /* ==============================================================
               CSS FINAL: FLEXBOX STRETCH - ÉP BUNG KÍCH THƯỚC TUYỆT ĐỐI
               ============================================================== */
            div[data-testid="stButton"] { width: 100% !important; }
            
            /* 1. NÚT CHÍNH: Ép thành Flexbox chạy dọc và dãn ngang tối đa */
            [data-testid="stBaseButton-secondary"] {
                display: flex !important; 
                flex-direction: column !important;
                align-items: stretch !important; /* Dãn chiều ngang 100% */
                
                width: 100% !important; 
                height: 175px !important; min-height: 175px !important; 
                padding: 0 !important; 
                border-radius: 12px !important; background-color: #121418 !important; 
                border: 1px solid rgba(255, 255, 255, 0.1) !important;
                position: relative !important; z-index: 0 !important;
                overflow: hidden !important; transition: transform 0.2s, border-color 0.2s !important;
            }
            [data-testid="stBaseButton-secondary"]:hover { border-color: #ff4b4b !important; transform: translateY(-4px) !important; box-shadow: 0 8px 24px rgba(255, 75, 75, 0.15) !important; }

            /* 2. CHẶN NỀN ĐEN: Mọi wrapper trung gian đều phải trong suốt */
            [data-testid="stBaseButton-secondary"] * { background-color: transparent !important; }

            /* 3. WRAPPER TRUNG GIAN: Ép chúng kế thừa tính "dãn nở" của nút mẹ */
            [data-testid="stBaseButton-secondary"] > span,
            [data-testid="stBaseButton-secondary"] > div,
            [data-testid="stBaseButton-secondary"] div[data-testid="stMarkdownContainer"] {
                display: flex !important;
                flex-direction: column !important;
                align-items: stretch !important; /* Tiếp tục ép dãn xuống lớp con */
                flex: 1 1 100% !important;
                width: 100% !important; max-width: 100% !important; 
                height: 100% !important; 
                padding: 0 !important; margin: 0 !important;
            }

            /* 4. KHUNG CHỨA TEXT (THẺ P): Khối Grid nay đã bự bằng nút */
            [data-testid="stBaseButton-secondary"] p {
                display: grid !important; 
                flex: 1 1 100% !important;
                width: 100% !important; max-width: 100% !important; 
                height: 100% !important; 
                margin: 0 !important; padding: 1.2rem !important; box-sizing: border-box !important;
                
                /* Đặt cột giữa là 1fr để chiếm trọn phần rỗng, đẩy 2 cột còn lại về 2 mép */
                grid-template-columns: 45px 1fr 95px !important;
                grid-template-rows: auto auto 1fr auto auto auto !important;
                grid-template-areas: "flag event round" "flag loc round" "divider divider divider" "date date status" "win1 win1 status" "win2 win2 status" !important;
                row-gap: 4px !important; column-gap: 8px !important; align-items: center !important;
            }

            /* 5. ẢNH NỀN */
            [data-testid="stBaseButton-secondary"] img[alt="bg"] {
                position: absolute !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
                width: 100% !important; height: 100% !important; min-width: 100% !important; min-height: 100% !important; max-width: none !important; max-height: none !important;
                object-fit: cover !important; object-position: center !important; 
                opacity: 0.45 !important; z-index: 1 !important; transform: scale(1.05) !important; pointer-events: none !important; display: block !important; margin: 0 !important; padding: 0 !important;
            }

            /* 6. CÁC THÀNH PHẦN GRID */
            [data-testid="stBaseButton-secondary"] p img[alt="f"],
            [data-testid="stBaseButton-secondary"] p img[alt="d"],
            [data-testid="stBaseButton-secondary"] p strong,
            [data-testid="stBaseButton-secondary"] p em,
            [data-testid="stBaseButton-secondary"] p code,
            [data-testid="stBaseButton-secondary"] p del {
                position: relative !important; z-index: 2 !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.9);
            }

            /* CỘT 1 (Trái) */
            [data-testid="stBaseButton-secondary"] p img[alt="f"] { grid-area: flag; width: 36px !important; height: 26px !important; border-radius: 4px !important; object-fit: cover !important; justify-self: start !important; align-self: center !important; box-shadow: 0 0 3px rgba(255,255,255,0.2) !important; }
            
            /* ĐƯỜNG KẺ NỐI DÀI */
            [data-testid="stBaseButton-secondary"] p img[alt="d"] { grid-area: divider; width: calc(100% + 2.4rem) !important; height: 1px !important; background-color: rgba(255,255,255,0.25) !important; margin-top: auto !important; margin-bottom: auto !important; margin-left: -1.2rem !important; margin-right: -1.2rem !important; box-shadow: none !important; }
            
            /* CỘT 2 (Giữa, sát mép trái Cột 1) */
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(1), [data-testid="stBaseButton-secondary"] p em:nth-of-type(1), [data-testid="stBaseButton-secondary"] p code:nth-of-type(1), [data-testid="stBaseButton-secondary"] p strong:nth-of-type(2), [data-testid="stBaseButton-secondary"] p em:nth-of-type(2) { justify-self: start !important; text-align: left !important; width: 100% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(1) { grid-area: event; font-size: 1.05rem !important; color: #ffffff !important; line-height: 1.2 !important; }
            [data-testid="stBaseButton-secondary"] p em:nth-of-type(1) { grid-area: loc; font-size: 0.85rem !important; color: #d0d0d0 !important; font-style: normal !important; }
            [data-testid="stBaseButton-secondary"] p code:nth-of-type(1) { grid-area: date; font-size: 0.85rem !important; color: #ffffff !important; background: transparent !important; padding: 0 !important; font-family: inherit !important; font-weight: 800 !important; text-shadow: none !important;}
            [data-testid="stBaseButton-secondary"] p strong:nth-of-type(2) { grid-area: win1; font-size: 0.9rem !important; color: #e0e0e0 !important; margin-top: 4px !important; }
            [data-testid="stBaseButton-secondary"] p em:nth-of-type(2) { grid-area: win2; font-size: 0.85rem !important; color: #d0d0d0 !important; font-style: normal !important; }
            
            /* CỘT 3 (Phải, bám sát lề phải của nút) */
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(1), [data-testid="stBaseButton-secondary"] p del:nth-of-type(2) { justify-self: end !important; text-align: right !important; text-decoration: none !important; font-weight: bold !important; color: #ffffff !important; }
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(1) { grid-area: round; font-size: 0.9rem !important; background-color: rgba(255, 255, 255, 0.15) !important; padding: 4px 10px !important; border-radius: 20px !important; }
            [data-testid="stBaseButton-secondary"] p del:nth-of-type(2) { grid-area: status; font-size: 0.8rem !important; background: transparent !important; padding: 4px 8px !important; border-radius: 6px !important; border: none !important; min-width: 80px !important; align-self: end !important; text-align: center !important; }
        </style>
    """, unsafe_allow_html=True)

    col_back, col_title, col_sel = st.columns([0.15, 3.5, 1.2], vertical_alignment="center")
    
    with col_back:
        if st.button("←", key="btn_back_home", type="primary"):
            st.switch_page("pages/home.py")
            
    with col_title:
        st.markdown("<h2 style='margin: 0; padding: 0;'> Race Calendar & Results</h2>", unsafe_allow_html=True)
        
    with col_sel:
        if 'selected_year' not in st.session_state:
            st.session_state['selected_year'] = 2026
            
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 0
        
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
                    
                    # 3. LẤY ẢNH NỀN THEO TÊN SỰ KIỆN
                    raw_bg_path = TRACK_BGS.get(event_name)
                    bg_url = load_bg_image(raw_bg_path)
                    
                    now = datetime.now()
                    event_date = event['EventDate'].tz_localize(None) if pd.notna(event['EventDate']) else None
                    date_str = event_date.strftime("%d %b, %Y") if event_date else "TBA"
                    
                    format_type = str(event.get('EventFormat', 'conventional')).capitalize().replace('_', ' ')
                    if not format_type: format_type = "Conventional"
                    elif format_type in ['Sprint', 'Sprint qualifying'] : format_type = "Sprint Weekend"
                    
                    status_text = "Upcoming"
                    is_completed = False
                    line1 = ""
                    line2 = ""
                    
                    if event_date:
                        time_diff = (now - event_date).total_seconds()
                        if time_diff > 10800:
                            status_text = "Completed"
                            is_completed = True
                            winner_info = get_race_winner(selected_year, round_num)
                            if winner_info == "N/A":
                                status_text = "Cancelled"
                                is_completed = False
                                line1 = "Format: " + format_type 
                            elif "(" in winner_info:
                                w_name, w_team = winner_info.split(" (")
                                line1 = f"{w_name.strip()}"
                                line2 = f"{w_team.replace(')', '').strip()}"
                            else:
                                line1 = f"{winner_info}"; line2 = "N/A"
                        elif time_diff > 0:
                            status_text = "Ongoing"; line1 = "Format: " + format_type
                        else:
                            line1 = "Format: " + format_type
                    else:
                        line1 = "Format: "
                            
                    current_flag = flag_url if flag_url else div_img
                    
                    # 4. CHÈN `![bg]({bg_url})` VÀO ĐẦU LABEL ĐỂ TẠO ẢNH NỀN
                    if status_text == "Upcoming":
                        btn_label = f"![bg]({bg_url})![f]({current_flag})__{event_name}__*{location}*~Round {round_num}~![d]({div_img})``{date_str}``__{line1}__~{status_text}~"
                    else:
                        btn_label = f"![bg]({bg_url})![f]({current_flag})__{event_name}__*{location}*~Round {round_num}~![d]({div_img})``{date_str}``__{line1}__*{line2}*~{status_text}~"
                    
                    with col:
                        if st.button(btn_label, key=f"btn_ra_{selected_year}_{round_num}", use_container_width=True, disabled=not is_completed):
                            st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                            st.switch_page("pages/details.py")
    else:
        st.warning("No schedule data found for this season.")

render()