import streamlit as st
import pandas as pd
import requests
import base64
import os
import unicodedata

# Cấu hình màu sắc đặc trưng của các đội đua
TEAM_COLORS = {
    "red bull": "#3671C6", "mercedes": "#00D2BE", "ferrari": "#DC0000",
    "mclaren": "#FF8000", "aston martin": "#229971", "alpine": "#0090FF",
    "williams": "#37BEDD", "rb": "#6692FF", "alphatauri": "#2B4562",
    "haas": "#FFFFFF", "sauber": "#52E252", "alfa romeo": "#900000",
    "kick": "#52E252", "racing bulls": "#6692FF"
}

@st.cache_data(show_spinner=False)
def get_image_base64(path):
    """Mã hóa ảnh thành Base64 để nhúng vào HTML"""
    if path and isinstance(path, str) and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = path.split('.')[-1].lower()
            mime_types = {"avif": "image/avif", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
            mime = mime_types.get(ext, "image/png")
            return f"data:{mime};base64,{b64}"
    return None

def normalize_name(name):
    """Xóa dấu (VD: Pérez -> Perez) để dễ tìm tên file ảnh"""
    nfkd_form = unicodedata.normalize('NFKD', name)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower().replace(" ", "")

def get_driver_image_b64(first_name, last_name):
    """Tìm ảnh tay đua trong thư mục assets/drivers/"""
    last_norm = normalize_name(last_name)
    first_norm = normalize_name(first_name)
    
    possible_paths = [
        f"assets/drivers/{last_norm}.avif", f"assets/drivers/{last_norm}.png",
        f"assets/drivers/{first_norm}{last_norm}.avif", f"assets/drivers/{first_norm}{last_norm}.png",
        f"assets/Drivers/{last_norm}.avif", f"assets/Drivers/{last_norm}.png",
    ]
    for path in possible_paths:
        b64 = get_image_base64(path)
        if b64: return b64
    return None

def get_team_logo_b64(team_name):
    """Tìm ảnh logo đội đua trong thư mục assets/teams/"""
    team_lower = str(team_name).lower().strip()
    possible_paths = [
        f"assets/teams/{team_name}.avif", f"assets/teams/{team_lower}.avif", f"assets/teams/{team_lower.replace(' ', '')}.avif",
        f"assets/Teams/{team_name}.avif", f"assets/Teams/{team_lower}.avif", f"assets/Teams/{team_lower.replace(' ', '')}.avif"
    ]
    for path in possible_paths:
        b64 = get_image_base64(path)
        if b64: return b64
    return None

def get_team_color(team_name):
    team_lower = str(team_name).lower()
    for key, color in TEAM_COLORS.items():
        if key in team_lower: return color
    return "#555555"

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_all_driver_standings(year):
    """Lấy Bảng xếp hạng TẤT CẢ tay đua của năm từ API cùng với số Podiums"""
    drivers_data = []
    try:
        # Bước 1: Quét toàn bộ kết quả chặng đua của năm để đếm số Podiums (Top 3)
        podium_counts = {}
        try:
            res_url = f"https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=1000"
            res_data = requests.get(res_url, timeout=8).json()
            races = res_data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
            for race in races:
                for result in race.get('Results', []):
                    # Nếu vị trí <= 3 thì cộng 1 vào bộ đếm Podium của tay đua đó
                    if int(result.get('position', 100)) <= 3:
                        d_id = result.get('Driver', {}).get('driverId')
                        podium_counts[d_id] = podium_counts.get(d_id, 0) + 1
        except Exception:
            pass # Nếu có lỗi khi lấy kết quả, podium tạm coi là 0 để không làm sập tab
            
        # Bước 2: Lấy Bảng xếp hạng tay đua chính thức (Points, Wins, Position)
        url = f"https://api.jolpi.ca/ergast/f1/{year}/driverStandings.json?limit=100"
        res = requests.get(url, timeout=5).json()
        dr_lists = res.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
        
        if dr_lists:
            standings = dr_lists[0].get('DriverStandings', [])
            for d in standings:
                drv_info = d['Driver']
                driver_id = drv_info.get('driverId', '')
                constructor_name = d['Constructors'][0]['name'] if d['Constructors'] else "Unknown"
                
                # Gắn số Podium đếm được ở Bước 1 vào dữ liệu
                total_podiums = podium_counts.get(driver_id, 0)
                
                drivers_data.append({
                    "pos": d['position'],
                    "points": d['points'],
                    "wins": d.get('wins', '0'),
                    "podiums": str(total_podiums), 
                    "first_name": drv_info['givenName'],
                    "last_name": drv_info['familyName'],
                    "number": drv_info.get('permanentNumber', ''),
                    "team": constructor_name
                })
    except Exception:
        pass
    return drivers_data

def render():
    st.markdown("""
        <style>
            /* ==============================================================
               CSS ĐỒNG BỘ LAYOUT VÀ NAVBAR GIỐNG HỆT TRANG HOME
               ============================================================== */
            
            /* 1. Đồng bộ khoảng cách lề và độ rộng màn hình */
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            
            /* 2. Đồng bộ design nút Navbar (Nút Primary) */
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; border: 1px solid #ff4b4b !important; color: #ff4b4b !important;
                border-radius: 20px !important; padding: 0px 15px !important; font-size: 0.85rem !important;
                height: 32px !important; min-height: 32px !important; font-weight: bold !important;
                transition: all 0.2s ease-in-out !important;
            }
            [data-testid="stBaseButton-primary"]:hover { 
                background-color: rgba(255, 75, 75, 0.1) !important; transform: translateY(-2px) !important; 
            }

            /* ==============================================================
               CSS CHO THẺ DRIVER CARD TƯƠNG TỰ ẢNH THIẾT KẾ
               ============================================================== */
            .drv-card {
                display: flex;
                background: linear-gradient(135deg, #1e2025 0%, #121418 100%);
                border-radius: 12px;
                margin-bottom: 1.2rem;
                position: relative;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.05);
                height: 150px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .drv-card:hover {
                transform: translateY(-4px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.5);
                border-color: rgba(255,255,255,0.1);
            }
            
            /* Thông tin bên trái (Thêm padding phải 130px để text không bị hình tay đua đè lên) */
            .drv-info {
                padding: 15px 130px 15px 20px;
                flex: 1;
                display: flex;
                flex-direction: column;
                z-index: 2;
            }
            
            /* Dòng trên cùng: Rank + Tên tay đua ngang hàng */
            .drv-main-row {
                display: flex;
                align-items: baseline;
                gap: 12px;
            }
            .drv-rank {
                font-size: 2.8rem;
                font-weight: 900;
                color: rgba(255,255,255,0.9);
                line-height: 1;
                font-style: italic;
                min-width: 40px;
            }
            .drv-fname {
                font-size: 1.25rem;
                color: #d0d0d0;
                font-weight: 500;
            }
            .drv-lname {
                font-size: 1.6rem;
                font-weight: 900;
                color: #ffffff;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            /* Dòng bên dưới: Team, Wins, Podiums, Points */
            .drv-stats-row {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 12px;
                margin-top: auto; /* Đẩy xuống dưới cùng của thẻ */
                margin-bottom: 5px;
            }
            .drv-team {
                display: flex;
                align-items: center;
                gap: 10px;
                padding-right: 12px;
                border-right: 1px solid rgba(255,255,255,0.2);
            }
            .drv-team-logo {
                height: 24px;
                object-fit: contain;
                opacity: 0.9;
            }
            .drv-team-name {
                font-size: 0.9rem;
                color: #888;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .drv-stat-item {
                font-size: 0.85rem;
                color: #a0a0a0;
                font-weight: 600;
                display: flex;
                gap: 4px;
            }
            .drv-stat-val {
                color: #ffffff;
                font-weight: bold;
            }
            .drv-points {
                font-size: 1rem;
                font-weight: 900;
                color: #00cc66;
                background: rgba(255,255,255,0.1);
                padding: 3px 10px;
                border-radius: 12px;
                margin-left: 5px;
            }
            
            /* Nền mờ (Watermark) và ảnh chân dung bên phải */
            .drv-bg-number {
                position: absolute;
                right: 20px;
                bottom: -35px;
                font-size: 8.5rem;
                font-weight: 900;
                color: rgba(255,255,255,0.15); /* LÀM SÁNG SỐ XE */
                z-index: 0;
                line-height: 1;
                font-style: italic;
                user-select: none;
            }
            .drv-portrait {
                position: absolute;
                right: -10px;
                bottom: 0;
                height: 125%;
                z-index: 1;
                opacity: 0.95;
                mask-image: linear-gradient(to right, transparent 0%, black 40%);
                -webkit-mask-image: linear-gradient(to right, transparent 0%, black 40%);
            }
        </style>
    """, unsafe_allow_html=True)

    # --- Header ---
    col_back, col_hdr1, col_hdr2 = st.columns([0.15, 3.5, 1.2])
    
    with col_back:
        st.write("") 
        if st.button("←", key="back_home_btn_drv"):
            st.switch_page("pages/home.py")
            
    with col_hdr1:
        if 'selected_year' not in st.session_state: st.session_state['selected_year'] = 2024
        st.markdown(f"<h2 style='margin-top: 0;'>Driver Standings {st.session_state['selected_year']}</h2>", unsafe_allow_html=True)
        
    with col_hdr2:
        years_list = [2026, 2025, 2024, 2023, 2022, 2021]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 2
        st.session_state['selected_year'] = st.selectbox("Season", years_list, index=safe_index, label_visibility="collapsed")

    st.divider()

    # Lấy dữ liệu API
    drivers_data = fetch_all_driver_standings(st.session_state['selected_year'])
    
    if not drivers_data:
        st.info(f"Chưa có dữ liệu xếp hạng tay đua cho mùa giải {st.session_state['selected_year']}.")
        return

    # Vẽ giao diện Grid 2 cột
    col1, col2 = st.columns(2)
    
    for i, d in enumerate(drivers_data):
        target_col = col1 if i % 2 == 0 else col2
        team_color = get_team_color(d["team"])
        
        # Lấy logo team
        logo_b64 = get_team_logo_b64(d["team"])
        team_html = f"<img src='{logo_b64}' class='drv-team-logo'>" if logo_b64 else f"<span class='drv-team-name'>{d['team']}</span>"
        
        # Lấy ảnh chân dung (Portrait)
        portrait_b64 = get_driver_image_b64(d["first_name"], d["last_name"])
        portrait_html = f"<img src='{portrait_b64}' class='drv-portrait'>" if portrait_b64 else ""

        # Sinh mã HTML cho thẻ Card
        card_html = f"""<div class='drv-card' style='border-left: 6px solid {team_color};'>
<div class='drv-info'>
<div class='drv-main-row'>
<span class='drv-rank'>{d['pos']}</span>
<span class='drv-fname'>{d['first_name']}</span>
<span class='drv-lname'>{d['last_name']}</span>
</div>
<div class='drv-stats-row'>
<div class='drv-team'>{team_html}</div>
<span class='drv-stat-item'>Wins: <span class='drv-stat-val'>{d['wins']}</span></span>
<span class='drv-stat-item'>Podiums: <span class='drv-stat-val'>{d['podiums']}</span></span>
<span class='drv-points'>{d['points']} PTS</span>
</div>
</div>
<div class='drv-bg-number'>{d['number']}</div>
{portrait_html}
</div>"""
        
        target_col.markdown(card_html, unsafe_allow_html=True)

render()