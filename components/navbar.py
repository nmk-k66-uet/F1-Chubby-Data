import streamlit as st
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

from core.data_loader import get_schedule
from core.config import get_flag_url

def nav_to(page_path):
    try:
        st.switch_page(f"pages/{page_path}.py")
    except Exception:
        st.toast(f"Functions under development: {page_path}", icon="🚧")

def render_navbar():
    st.markdown("""
        <style>
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
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)

    # ==========================================
    # TOP NAVIGATION BAR LAYOUT
    # Mở rộng cột Next Session (4.0) để tên không bị che
    # ==========================================
    col_logo, col_next, col_n1, col_n2, col_n3, col_n4 = st.columns([0.9, 1.3, 1.0, 1.0, 1.0, 1.0], vertical_alignment="center")
    
    with col_logo:
        st.markdown("""
            <div style="display: flex; align-items: center;">
                <span style="font-size: 2rem; margin-right: 12px; line-height: 1;">🏎️</span>
                <div style="display: flex; flex-direction: column;">
                    <span style="font-size: 1.3rem; font-weight: 900; letter-spacing: 1px; color: #ffffff; line-height: 1;">F1 PULSE</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with col_next:
        now = datetime.now()
        schedule = get_schedule(now.year)
        
        if schedule is not None and not schedule.empty and 'EventDate' in schedule.columns:
            future_events = schedule[schedule['EventDate'].dt.tz_localize(None) > now]
            
            if not future_events.empty:
                next_event = future_events.iloc[0]
                country = str(next_event['Country'])
                event_name = str(next_event['EventName'])
                event_date = next_event['EventDate'].tz_localize(None)
                flag_url = get_flag_url(country)
                
                # Tính khoảng cách mili-giây đẩy xuống cho Javascript xử lý Live Countdown
                diff_seconds = (event_date - now).total_seconds()
                
                # Sử dụng HTML iframe với Javascript nội tuyến để tự động đếm ngược mỗi giây
                live_timer_html = f"""
                <style>
                    body {{
                        margin: 0; padding: 0; font-family: "Source Sans Pro", sans-serif;
                        background-color: transparent; color: white; overflow: hidden;
                    }}
                    .box {{
                        display: flex; align-items: center; background: rgba(255,255,255,0.05);
                        padding: 4px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);
                        height: 35px; /* Vừa khít với height=45 của Streamlit iframe */
                    }}
                    .flag {{ height: 20px; border-radius: 3px; margin-right: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.5); }}
                    .info {{
                        display: flex; flex-direction: column; justify-content: center;
                        margin-right: 15px; border-right: 1px solid rgba(255,255,255,0.1);
                        padding-right: 15px; flex-grow: 1; overflow: hidden; white-space: nowrap;
                    }}
                    .label {{ font-size: 0.65rem; color: #a0a0a0; text-transform: uppercase; letter-spacing: 1px; line-height: 1.2; }}
                    /* Bỏ max-width, dùng text-overflow để tự động cắt nếu thực sự quá dài */
                    .val-name {{ font-size: 0.85rem; font-weight: bold; color: #ffffff; line-height: 1.2; text-overflow: ellipsis; overflow: hidden; }}
                    .val-time {{ font-size: 0.95rem; font-weight: 900; color: #ff4b4b; font-family: monospace; line-height: 1.2; white-space: nowrap; }}
                </style>
                
                <div class="box">
                    <img src="{flag_url}" class="flag"/>
                    <div class="info">
                        <span class="label">Next Session</span>
                        <span class="val-name" title="{country} - {event_name}">{country} - {event_name}</span>
                    </div>
                    <div style="display: flex; flex-direction: column; justify-content: center; min-width: 90px;">
                        <span class="label">Starts In</span>
                        <span class="val-time" id="live-timer">--d --h --m --s</span>
                    </div>
                </div>
                
                <script>
                    // Truyền khoảng thời gian từ Python vào JS
                    var targetTime = new Date().getTime() + ({diff_seconds} * 1000);
                    
                    function updateTimer() {{
                        var now = new Date().getTime();
                        var distance = targetTime - now;
                        
                        if (distance < 0) {{
                            document.getElementById("live-timer").innerHTML = "LIVE";
                            return;
                        }}
                        
                        var d = Math.floor(distance / (1000 * 60 * 60 * 24));
                        var h = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                        var m = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                        var s = Math.floor((distance % (1000 * 60)) / 1000);
                        
                        // Rút gọn thành d, h, m, s
                        document.getElementById("live-timer").innerHTML = d + "d " + h + "h " + m + "m " + s + "s";
                    }}
                    
                    // Cập nhật mỗi giây
                    setInterval(updateTimer, 1000);
                    updateTimer();
                </script>
                """
                
                # Render HTML Iframe trong cột
                components.html(live_timer_html, height=45)
                
            else:
                st.markdown("<div style='height: 45px; display: flex; align-items: center; color: #888;'>Season Completed</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='height: 45px; display: flex; align-items: center; color: #888;'>Schedule Unavailable</div>", unsafe_allow_html=True)
            
    with col_n1:
        if st.button("Home", type="primary", use_container_width=True): nav_to("home")
    with col_n2:
        if st.button("Drivers", type="primary", use_container_width=True): nav_to("drivers")
    with col_n3:
        if st.button("Constructors", type="primary", use_container_width=True): nav_to("constructors")
    with col_n4:
        if st.button("Race Analytics", type="primary", use_container_width=True): nav_to("race_analytics")

    # Đường phân cách Top Bar
    st.markdown("<hr style='margin: 5px 0 15px 0; border-color: rgba(255,255,255,0.1);'>", unsafe_allow_html=True)