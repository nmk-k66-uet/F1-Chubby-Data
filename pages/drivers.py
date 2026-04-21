"""Drivers Page - Driver Details and Performance Analysis

Detailed view of individual driver performance:
- Driver selection interface
- Race-by-race results comparison
- In-race analytics and telemetry visualization
- Live race predictions and analysis
- Interactive replay engine

"""

import streamlit as st
import pandas as pd
import base64
import os
import unicodedata
from core import db

# Cấu hình màu sắc đặc trưng của các đội đua
TEAM_COLORS = {
    "red bull": "#3671C6", "mercedes": "#00D2BE", "ferrari": "#DC0000",
    "mclaren": "#FF8000", "aston martin": "#229971", "alpine": "#0090FF",
    "williams": "#37BEDD", "rb": "#6692FF", "alphatauri": "#2B4562",
    "haas": "#FFFFFF", "sauber": "#52E252", "alfa romeo": "#900000",
    "kick": "#52E252", "racing bulls": "#6692FF"
}

def get_image_base64(path):
    """Mã hóa ảnh thành Base64 để nhúng vào HTML"""
    if path and isinstance(path, str) and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = path.split('.')[-1].lower()
            mime_types = {"avif": "image/avif"}
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
    path = f"assets/drivers/{first_norm} {last_norm}.avif"
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
    """Fetch all driver standings from PostgreSQL, fallback to Ergast API."""
    drivers_data = []

    # --- Try PostgreSQL first ---
    max_round_rows = db.query(
        "SELECT MAX(round) as max_round FROM driver_standings WHERE year=%s", (year,)
    )
    max_round = max_round_rows[0]["max_round"] if max_round_rows and max_round_rows[0]["max_round"] else None

    if max_round is not None:
        d_rows = db.query(
            "SELECT ds.full_name, ds.team_name, ds.position, ds.points, ds.wins, ds.driver_abbr, "
            "COALESCE(pod.podiums, 0) as podiums "
            "FROM driver_standings ds "
            "LEFT JOIN ("
            "  SELECT driver_abbr, COUNT(*) as podiums "
            "  FROM session_results "
            "  WHERE year=%s AND session_type='R' AND position <= 3 "
            "  GROUP BY driver_abbr"
            ") pod ON ds.driver_abbr = pod.driver_abbr "
            "WHERE ds.year=%s AND ds.round=%s "
            "ORDER BY ds.position",
            (year, year, max_round),
        )
        if d_rows:
            for d in d_rows:
                name_parts = d["full_name"].split(" ", 1)
                first_name = name_parts[0] if name_parts else ""
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                drivers_data.append({
                    "pos": str(d["position"]),
                    "points": str(int(d["points"])) if d["points"] == int(d["points"]) else str(d["points"]),
                    "wins": str(d["wins"]),
                    "podiums": str(d["podiums"]),
                    "first_name": first_name,
                    "last_name": last_name,
                    "number": "",
                    "team": d["team_name"],
                })
            return drivers_data

    # --- Fallback: Ergast API ---
    import requests as _requests
    try:
        podium_counts = {}
        try:
            res_url = f"https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=1000"
            res_data = _requests.get(res_url, timeout=8).json()
            races = res_data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
            for race in races:
                for result in race.get('Results', []):
                    if int(result.get('position', 100)) <= 3:
                        d_id = result.get('Driver', {}).get('driverId')
                        podium_counts[d_id] = podium_counts.get(d_id, 0) + 1
        except Exception:
            pass
            
        url = f"https://api.jolpi.ca/ergast/f1/{year}/driverStandings.json?limit=100"
        res = _requests.get(url, timeout=5).json()
        dr_lists = res.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
        
        if dr_lists:
            standings = dr_lists[0].get('DriverStandings', [])
            for d in standings:
                drv_info = d['Driver']
                driver_id = drv_info.get('driverId', '')
                constructor_name = d['Constructors'][0]['name'] if d['Constructors'] else "Unknown"
                
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
    """Render the complete driver details page with race data tabs.
    
    Output: Displays driver selection interface and multiple tabs for:
    - Results: Qualifying and race results
    - Lap Times: Lap-by-lap timing comparison
    - Telemetry: Speed, throttle, brake, RPM, and DRS data
    - Live Race: Real-time race predictions and momentum analysis
    - Replay: Interactive race replay visualization
    """
    if 'selected_year' not in st.session_state: 
        st.session_state['selected_year'] = 2026

    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            
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
               CSS DRIVER CARD
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
                right: 150px;
                bottom: -300px;
                height: 300%;
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

    with col_hdr2:
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 0
        st.session_state['selected_year'] = st.selectbox("Season", years_list, index=safe_index, label_visibility="collapsed")

    with col_hdr1:
        if 'selected_year' not in st.session_state: st.session_state['selected_year'] = 2026
        st.markdown(f"<h2 style='margin-top: 0;'>Driver Standings {st.session_state['selected_year']}</h2>", unsafe_allow_html=True)
        
    st.divider()

    drivers_data = fetch_all_driver_standings(st.session_state['selected_year'])
    
    if not drivers_data:
        st.info(f"No data for season {st.session_state['selected_year']}.")
        return

    col1, col2 = st.columns(2)
    
    for i, d in enumerate(drivers_data):
        target_col = col1 if i % 2 == 0 else col2
        team_color = get_team_color(d["team"])
        
        # Lấy logo team
        logo_b64 = get_team_logo_b64(d["team"])
        team_html = f"<img src='{logo_b64}' class='drv-team-logo'>" if logo_b64 else f"<span class='drv-team-name'>{d['team']}</span>"
        
        # Portrait
        if st.session_state['selected_year'] == 2026:
            portrait_b64 = get_driver_image_b64(d["first_name"], d["last_name"])
            portrait_html = f"<img src='{portrait_b64}' class='drv-portrait'>" if portrait_b64 else ""
        else:
            portrait_html = ""

        # HTML Card
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