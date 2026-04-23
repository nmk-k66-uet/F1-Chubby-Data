"""Home Page - F1 Season Overview Dashboard

Displays the current F1 season standings and upcoming race calendar:
- Constructor and Driver standings (top 4)
- Upcoming race schedule with details
- Season year selector
- Links to full standings pages
"""

import streamlit as st
import pandas as pd
import base64
import os
from datetime import datetime
from core.data_loader import get_schedule, get_race_winner
from core.config import get_flag_url

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
    """Convert local image file to base64 data URL for embedding in HTML.
    
    Args:
        path (str): File path to image (supports .avif, .jpg, .jpeg formats).
    
    Returns:
        str: Data URL string (e.g., 'data:image/avif;base64,...') or None if file not found.
    
    Output: Base64 encoded image data suitable for HTML img tags.
    """
    if path and isinstance(path, str) and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            ext = path.split('.')[-1].lower()
            mime_types = {"avif": "image/avif"}
            mime = mime_types.get(ext, "image/jpeg")
            return f"data:{mime};base64,{b64}"
    return None

def get_team_logo_html(team_name):
    """Generate HTML image tag for team logo with fallback to team abbreviation.
    
    Searches multiple path patterns and returns formatted HTML img tag or abbreviation badge.
    
    Args:
        team_name (str): Name of the F1 team.
    
    Returns:
        str: HTML img tag with base64 image or fallback div with team abbreviation.
    
    Output: Styled HTML element ready for rendering in Streamlit markdown.
    """
    team_lower = str(team_name).lower().strip()
    
    possible_paths = [
        f"assets/teams/{team_name}.avif",
        f"assets/teams/{team_lower}.avif",
        f"assets/teams/{team_lower.replace(' ', '')}.avif",
        f"assets/Teams/{team_name}.avif",
        f"assets/Teams/{team_lower}.avif",
        f"assets/Teams/{team_lower.replace(' ', '')}.avif"
    ]
    
    for path in possible_paths:
        logo_b64 = get_image_base64(path)
        if logo_b64:
            return f"<img src='{logo_b64}' style='height: 38px; width: auto; max-width: 70px; object-fit: contain; filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.6)); opacity: 0.9;'/>"
            
    return f"<div class='st-logo' style='color:#ffffff; font-size:1.2rem; font-weight:bold;'>{str(team_name)[:3].upper()}</div>"

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_standings(year):
    """Fetch Driver and Constructor standings from Ergast API."""
    drivers_data = []
    teams_data = []

    import requests as _requests
    try:
        dr_url = f"https://api.jolpi.ca/ergast/f1/{year}/driverStandings.json"
        dr_res = _requests.get(dr_url, timeout=5).json()
        dr_lists = dr_res.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
        
        if dr_lists:
            dr_standings = dr_lists[0].get('DriverStandings', [])
            for d in dr_standings[:4]:
                driver_name = f"{d['Driver']['givenName']} {d['Driver']['familyName']}"
                constructor_name = d['Constructors'][0]['name'] if d['Constructors'] else "N/A"
                
                drivers_data.append({
                    "name": driver_name,
                    "pts": d['points'],
                    "trend": f"P{d['position']}", 
                    "logo_html": get_team_logo_html(constructor_name)
                })
                
        cr_url = f"https://api.jolpi.ca/ergast/f1/{year}/constructorStandings.json"
        cr_res = _requests.get(cr_url, timeout=5).json()
        cr_lists = cr_res.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
        
        if cr_lists:
            cr_standings = cr_lists[0].get('ConstructorStandings', [])
            for c in cr_standings[:4]:
                team_name = c['Constructor']['name']
                
                teams_data.append({
                    "name": team_name,
                    "pts": c['points'],
                    "trend": f"P{c['position']}", 
                    "logo_html": get_team_logo_html(team_name)
                })
                
    except Exception:
        pass 
        
    return teams_data, drivers_data

def load_bg_image(path_or_url):
    """Load and convert background image to base64 data URL.
    
    Args:
        path_or_url (str): File path to image or URL.
    
    Returns:
        str: Base64 data URL for background image or default image if not found.
    
    Output: Data URL suitable for CSS background-image property.
    """
    if not path_or_url:
        return TRACK_BGS.get("Default", "")
    return get_image_base64(path_or_url)

def render():
    """Render the complete home page dashboard with standings and race calendar.
    
    Output: Displays full page with:
    - Season year selector
    - Constructor standings (top 4)
    - Driver standings (top 4)
    - Upcoming races calendar (this month + next month)
    - CSS styling for cards, buttons, and responsive layout
    
    CSS Sections:
    - .block-container: Page width and padding constraints
    - .sec-header, .sec-title: Section headers with accent color
    - .st-card: Standing position cards with hover effects
    - .st-info, .st-pts, .st-name, .st-trend: Card content styling
    - .st-logo: Team logo styling with filter effects
    - [data-testid="stBaseButton-secondary"]: Race card styling with background images
    - [data-testid="stBaseButton-primary"]: Action button styling with border and hover
    """
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; max-width: 95% !important; }
            .sec-header { display: flex; justify-content: space-between; align-items: flex-end; margin-top: 10px; margin-bottom: 15px; }
            .sec-title { color: #ffffff; font-size: 1.15rem; font-weight: 700; margin: 0; text-transform: uppercase; }
            .sec-title span { color: #ff4b4b; }
            
            /* CSS thẻ Bảng xếp hạng */
            .st-card {
                background-color: #16181c; border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px; padding: 18px 20px; display: flex; justify-content: space-between;
                align-items: center; margin-bottom: 15px; transition: transform 0.2s;
            }
            .st-card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.1); }
            .st-info { display: flex; flex-direction: column; }
            .st-pts { color: #ffffff; font-size: 1.4rem; font-weight: 900; }
            .st-name { color: #a0a0a0; font-size: 0.9rem; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;}
            .st-trend { color: #a0a0a0; font-size: 0.8rem; margin-top: 2px; font-weight: bold;}
            .st-logo { font-size: 1.8rem; opacity: 0.8; }

            /* CSS thẻ Chặng đua */
            [data-testid="stBaseButton-secondary"] * { background-color: transparent !important; }
            [data-testid="stBaseButton-secondary"] {
                width: 100% !important; display: block !important; height: 125px !important;
                border-radius: 12px !important; background-color: #121418 !important; 
                position: relative !important; overflow: hidden !important;
                border: 1px solid rgba(255, 255, 255, 0.1) !important;
                margin-bottom: 12px !important; transition: transform 0.2s, border-color 0.2s !important;
                padding: 0 !important; z-index: 0 !important;
            }
            [data-testid="stBaseButton-secondary"]:hover { border-color: #ff4b4b !important; transform: translateY(-3px) !important; box-shadow: 0 6px 20px rgba(255,75,75,0.2) !important;}
            [data-testid="stBaseButton-secondary"]:disabled { opacity: 0.7; filter: grayscale(70%); cursor: not-allowed !important; transform: none !important; }
            
            [data-testid="stBaseButton-secondary"] > div,
            [data-testid="stBaseButton-secondary"] div[data-testid="stMarkdownContainer"] {
                position: static !important; width: 100% !important; height: 100% !important; padding: 0 !important; margin: 0 !important;
            }

            [data-testid="stBaseButton-secondary"] p {
                position: static !important; display: flex !important; flex-direction: column !important; justify-content: center !important;
                width: 100% !important; height: 125px !important; margin: 0 !important; padding: 15px 20px !important;
                box-sizing: border-box !important; text-align: left !important; align-items: flex-start !important;
            }

            [data-testid="stBaseButton-secondary"] img[alt="bg"] {
                position: absolute !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
                width: 100% !important; height: 100% !important; min-width: 100% !important; min-height: 100% !important; max-width: none !important; max-height: none !important;
                object-fit: cover !important; object-position: center !important; 
                opacity: 0.65 !important; z-index: 1 !important; transform: scale(1.05) !important; pointer-events: none !important; display: block !important; margin: 0 !important; padding: 0 !important;
            }
            
            [data-testid="stBaseButton-secondary"] strong, [data-testid="stBaseButton-secondary"] em {
                position: relative !important; z-index: 2 !important; display: block !important; width: 100% !important; text-align: left !important;
                white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;
            }

            [data-testid="stBaseButton-secondary"] strong { font-size: 1.15rem !important; color: #ffffff !important; margin-bottom: 2px !important; text-shadow: 1px 1px 4px rgba(0,0,0,0.9); }
            [data-testid="stBaseButton-secondary"] em { font-size: 0.85rem !important; color: #d0d0d0 !important; font-style: normal !important; margin-bottom: 8px !important; text-shadow: 1px 1px 4px rgba(0,0,0,0.9); }
            
            /* BADGE TRẠNG THÁI: Nền trong suốt, không viền, chữ trắng */
            [data-testid="stBaseButton-secondary"] p del { 
                position: relative !important; z-index: 2 !important; display: inline-block !important; width: max-content !important; 
                font-size: 0.95rem !important; background-color: transparent !important; padding: 0 !important; 
                font-weight: 800 !important; text-decoration: none !important; border: none !important; box-shadow: none !important; color: #ffffff !important; text-shadow: 1px 1px 4px rgba(0,0,0,0.9);
            }
            
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important; border: 1px solid #ff4b4b !important; color: #ff4b4b !important;
                border-radius: 20px !important; padding: 0px 15px !important; font-size: 0.85rem !important;
                height: 32px !important; min-height: 32px !important; font-weight: bold !important;
            }
            [data-testid="stBaseButton-primary"]:hover { background-color: rgba(255, 75, 75, 0.1) !important; }
        </style>
    """, unsafe_allow_html=True)

    if 'selected_year' not in st.session_state:
        st.session_state['selected_year'] = 2026

    col_hdr1, col_hdr2 = st.columns([4, 1])

    
    with col_hdr2:
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        safe_index = years_list.index(st.session_state['selected_year']) if st.session_state['selected_year'] in years_list else 0
        st.session_state['selected_year'] = st.selectbox("Season", years_list, index=safe_index, label_visibility="collapsed")

    with col_hdr1:
        st.markdown(f"<h2 style='margin-top: 0;'>Season Overview {st.session_state['selected_year']}</h2>", unsafe_allow_html=True)

    col_left, col_right = st.columns([6.5, 3.5], gap="large")

    with col_left:

        api_teams, api_drivers = fetch_standings(st.session_state['selected_year'])
        
        teams_data = api_teams if api_teams else []
        drivers_data = api_drivers if api_drivers else []

        # 1. TEAM STANDINGS VÀ NÚT FULL STANDINGS
        col_t_title, col_t_btn = st.columns([3, 1.2])
        with col_t_title:
            st.markdown("<div class='sec-header'><div class='sec-title'>Constructor <span>Standings</span></div></div>", unsafe_allow_html=True)
        with col_t_btn:
            st.write("")
            if st.button("Full Standings →", key="btn_full_team", type="primary", use_container_width=True):
                st.switch_page("pages/constructors.py")
                    
        if not teams_data:
            st.info("Chưa có dữ liệu cho mùa giải này.")
        else:
            for i in range(0, len(teams_data), 2):
                c1, c2 = st.columns(2)
                with c1:
                    t1 = teams_data[i]
                    st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{t1['name']}</div><div class='st-pts'>{t1['pts']} PTS</div><div class='st-trend'>{t1['trend']}</div></div>{t1['logo_html']}</div>", unsafe_allow_html=True)
                with c2:
                    if i+1 < len(teams_data):
                        t2 = teams_data[i+1]
                        st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name'>{t2['name']}</div><div class='st-pts'>{t2['pts']} PTS</div><div class='st-trend'>{t2['trend']}</div></div>{t2['logo_html']}</div>", unsafe_allow_html=True)

        # 2. DRIVER STANDINGS VÀ NÚT FULL STANDINGS
        col_d_title, col_d_btn = st.columns([3, 1.2])
        with col_d_title:
            st.markdown("<div class='sec-header' style='margin-top: 25px;'><div class='sec-title'>Driver <span>Standings</span></div></div>", unsafe_allow_html=True)
        with col_d_btn:
            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
            if st.button("Full Standings →", key="btn_full_driver", type="primary", use_container_width=True):
                st.switch_page("pages/drivers.py")
                    
        if not drivers_data:
            st.info("Chưa có dữ liệu cho mùa giải này.")
        else:
            for i in range(0, len(drivers_data), 2):
                c1, c2 = st.columns(2)
                with c1:
                    d1 = drivers_data[i]
                    st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name' title='{d1['name']}'>{d1['name']}</div><div class='st-pts'>{d1['pts']} PTS</div><div class='st-trend'>{d1['trend']}</div></div>{d1['logo_html']}</div>", unsafe_allow_html=True)
                with c2:
                    if i+1 < len(drivers_data):
                        d2 = drivers_data[i+1]
                        st.markdown(f"<div class='st-card'><div class='st-info'><div class='st-name' title='{d2['name']}'>{d2['name']}</div><div class='st-pts'>{d2['pts']} PTS</div><div class='st-trend'>{d2['trend']}</div></div>{d2['logo_html']}</div>", unsafe_allow_html=True)

    with col_right:
        col_r_title, col_r_btn = st.columns([1.5, 1])
        with col_r_title:
            st.markdown("<div class='sec-header'><div class='sec-title'>Race <span>Highlights</span></div></div>", unsafe_allow_html=True)
        with col_r_btn:
            st.write("")
            if st.button("View All Races →", type="primary", use_container_width=True):
                st.session_state['play_intro'] = True
                st.switch_page("pages/race_analytics.py")
        
        events_df = get_schedule(st.session_state['selected_year'])
        if not events_df.empty:
            for _, event in events_df.head(4).iterrows():
                round_num = event['RoundNumber']
                event_name = str(event['EventName']).strip()
                country = str(event['Country'])
                
                raw_bg_path = TRACK_BGS.get(event_name)
                bg_url = load_bg_image(raw_bg_path)
                
                event_date = event['EventDate'].tz_localize(None) if pd.notna(event['EventDate']) else None
                date_str = event_date.strftime("%d %b, %Y") if event_date else "TBA"
                
                now = datetime.now()
                is_completed = False
                status_code = ""
                
                if event_date:
                    time_diff = (now - event_date).total_seconds()
                    if time_diff > 10800:
                        is_completed = True
                        winner = get_race_winner(st.session_state['selected_year'], round_num)
                        if winner == "N/A":
                            status_code = "~:red[CANCELLED]~"
                            is_completed = False
                        else:
                            winner_name = winner.split(" (")[0] if "(" in winner else winner
                            status_code = f"~Winner: {winner_name}~"
                    elif time_diff > 0:
                        status_code = "~:orange[LIVE NOW]~"
                    else:
                        status_code = "~:gray[UPCOMING]~"
                else:
                    status_code = "~:gray[TBA]~"

                # Cấu trúc: Ảnh Nền -> Tên Chặng -> Địa điểm -> Trạng thái
                btn_label = f"![bg]({bg_url})\n__{event_name}__\n*{date_str} - {country}*\n{status_code}"

                if st.button(btn_label, key=f"btn_dash_{st.session_state['selected_year']}_{round_num}", use_container_width=True, disabled=not is_completed):
                    st.session_state['selected_event'] = {'year': st.session_state['selected_year'], 'round': round_num, 'name': event_name, 'country': country}
                    st.switch_page("pages/details.py")
        else:
            st.warning("No races found.")

render()