import streamlit as st
import pandas as pd
import requests
import base64
import os

# Cấu hình màu sắc đặc trưng của các đội đua
TEAM_COLORS = {
    "red bull": "#3671C6", "mercedes": "#00D2BE", "ferrari": "#DC0000",
    "mclaren": "#FF8000", "aston martin": "#229971", "alpine": "#0090FF",
    "williams": "#37BEDD", "rb": "#6692FF", "alphatauri": "#2B4562",
    "haas": "#FFFFFF", "sauber": "#52E252", "alfa romeo": "#900000",
    "kick": "#52E252", "racing bulls": "#6692FF", "audi": "#E0E0E0", "cadillac": "#FFD700"
}

@st.cache_data(show_spinner=False)
def get_image_base64(path):
    if path and isinstance(path, str) and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = path.split('.')[-1].lower()
            mime_types = {"avif": "image/avif", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
            mime = mime_types.get(ext, "image/png")
            return f"data:{mime};base64,{b64}"
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

def get_car_image_b64(team_name, year):
    """Tìm ảnh xe đua trong thư mục assets/Cars/"""
    name_norm = str(team_name).lower().strip()
    
    # Rút gọn tên đội đua để map với file trong máy của bạn
    file_key = name_norm.replace(" ", "")
    if "red bull" in name_norm: file_key = "redbull"
    elif "haas" in name_norm: file_key = "haasf1team"
    elif "aston martin" in name_norm: file_key = "astonmartin"
    elif "rbf1team" == name_norm or "racing bulls" in name_norm: file_key = "rbf1team"
    elif "alpine" in name_norm: file_key = "alpinef1team"
    elif "williams" in name_norm: file_key = "williams"
    elif "mclaren" in name_norm: file_key = "mclaren"
    elif "ferrari" in name_norm: file_key = "ferrari"
    elif "mercedes" in name_norm: file_key = "mercedes"
    elif "audi" in name_norm or "sauber" in name_norm: file_key = "audi"
    elif "cadillac" in name_norm or "andretti" in name_norm: file_key = "cadillacf1team"

    possible_paths = [f"assets/Cars/{year}/{file_key}.avif",
        f"assets/Cars/2026/2026{file_key}carright.avif"]
    
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
def fetch_constructors_data(year):
    """Lấy Bảng xếp hạng Đội đua từ API và ghép với tên tay đua & số Podiums"""
    teams_data = []
    try:
        # Bước 1: Đếm số Podiums (Top 3) từ kết quả các chặng đua
        podium_counts = {}
        try:
            res_url = f"https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=1000"
            res_data = requests.get(res_url, timeout=8).json()
            races = res_data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
            for race in races:
                for result in race.get('Results', []):
                    if int(result.get('position', 100)) <= 3:
                        c_id = result.get('Constructor', {}).get('constructorId')
                        podium_counts[c_id] = podium_counts.get(c_id, 0) + 1
        except Exception: pass

        # Bước 2: Lấy Bảng xếp hạng đội đua
        cr_url = f"https://api.jolpi.ca/ergast/f1/{year}/constructorStandings.json?limit=100"
        cr_res = requests.get(cr_url, timeout=5).json()
        cr_lists = cr_res.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
        
        if cr_lists:
            for c in cr_lists[0].get('ConstructorStandings', []):
                cons_id = c['Constructor']['constructorId']
                teams_data.append({
                    "pos": c['position'],
                    "points": c['points'],
                    "wins": c.get('wins', '0'),
                    "podiums": str(podium_counts.get(cons_id, 0)),
                    "name": c['Constructor']['name']
                })
    except Exception: pass
    return teams_data

def render():
    if 'selected_year' not in st.session_state: 
        st.session_state['selected_year'] = 2026

    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; border: 1px solid #ff4b4b !important; color: #ff4b4b !important;
                border-radius: 20px !important; padding: 0px 15px !important; font-size: 0.85rem !important;
                height: 32px !important; min-height: 32px !important; font-weight: bold !important;
            }
            div.st-key-btn_back_home_cons button {
                background-color: transparent !important; border: 1px solid rgba(255, 255, 255, 0.2) !important;
                color: #a0a0a0 !important; border-radius: 50% !important; height: 42px !important; width: 42px !important;
                font-size: 1.2rem !important; display: flex !important; align-items: center !important; justify-content: center !important; margin-top: 0px !important;
            }
            .cons-card {
                display: flex; background: linear-gradient(135deg, #1e2025 0%, #121418 100%);
                border-radius: 12px; margin-bottom: 1.5rem; position: relative; overflow: hidden;
                border: 1px solid rgba(255,255,255,0.05); height: 160px; transition: transform 0.2s;
            }
            .cons-info { padding: 15px 20px; flex: 1; display: flex; flex-direction: column; justify-content: center; z-index: 2; max-width: 65%; }
            
            /* Dòng chính: Hạng | Tên đội */
            .cons-main-row { display: flex; align-items: baseline; gap: 15px; margin-bottom: 15px; }
            .cons-rank { font-size: 3rem; font-weight: 900; color: rgba(255,255,255,0.9); font-style: italic; line-height: 1; }
            .cons-name { font-size: 1.8rem; font-weight: 900; color: #ffffff; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px; }
            
            /* Dòng thông số: Logo | Points | Wins | Podiums */
            .cons-stats-row { display: flex; align-items: center; gap: 15px; }
            .cons-logo-box { height: 26px; display: flex; align-items: center; border-right: 1px solid rgba(255,255,255,0.2); padding-right: 15px; }
            .cons-logo { height: 24px; width: auto; object-fit: contain; }
            .cons-points { font-size: 1.05rem; font-weight: 900; color: #00cc66; background: rgba(255,255,255,0.1); padding: 4px 12px; border-radius: 12px; }
            .cons-stat-item { font-size: 0.95rem; color: #a0a0a0; font-weight: 600; display: flex; gap: 5px; align-items: baseline; }
            .cons-stat-val { color: #ffffff; font-weight: 800; font-size: 1.05rem; }
            
            .cons-car { position: absolute; right: -10px; bottom: 5px; height: 85%; width: auto; max-width: 55%; object-fit: contain; z-index: 1; filter: drop-shadow(-8px 10px 15px rgba(0,0,0,0.6)); pointer-events: none; }
        </style>
    """, unsafe_allow_html=True)

    col_back, col_title, col_sel = st.columns([0.15, 3.5, 1.2], vertical_alignment="center")
    with col_back:
        if st.button("←", key="btn_back_home_cons", type="primary"):
            st.switch_page("pages/home.py")
    with col_sel:
        if 'selected_year' not in st.session_state: st.session_state['selected_year'] = 2026
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 0
        st.session_state['selected_year'] = st.selectbox("Season", years_list, index=safe_index, label_visibility="collapsed")
    with col_title:
        st.markdown(f"<h2 style='margin: 0; padding: 0;'>Constructor Standings {st.session_state['selected_year']}</h2>", unsafe_allow_html=True)

    st.divider()
    teams_data = fetch_constructors_data(st.session_state['selected_year'])
    
    col1, col2 = st.columns(2)
    for i, t in enumerate(teams_data):
        target_col = col1 if i % 2 == 0 else col2
        team_color = get_team_color(t["name"])
        
        logo_b64 = get_team_logo_b64(t["name"])
        logo_html = f"<img src='{logo_b64}' class='cons-logo'>" if logo_b64 else ""
        
        if st.session_state['selected_year'] == 2026:
            car_b64 = get_car_image_b64(t["name"], st.session_state['selected_year'])
            car_html = f"<img src='{car_b64}' class='cons-car'>" if car_b64 else ""
        else:
            car_html = ""

        card_html = f"""<div class='cons-card' style='border-left: 8px solid {team_color};'>
<div class='cons-info'>
<div class='cons-main-row'>
<span class='cons-rank'>{t['pos']}</span>
<span class='cons-name' title='{t['name']}'>{t['name']}</span>
</div>
<div class='cons-stats-row'>
<div class='cons-logo-box'>{logo_html}</div>
<span class='cons-points'>{t['points']} PTS</span>
<span class='cons-stat-item'>Wins: <span class='cons-stat-val'>{t['wins']}</span></span>
<span class='cons-stat-item'>Podiums: <span class='cons-stat-val'>{t['podiums']}</span></span>
</div>
</div>
{car_html}
</div>"""
        target_col.markdown(card_html, unsafe_allow_html=True)

render()