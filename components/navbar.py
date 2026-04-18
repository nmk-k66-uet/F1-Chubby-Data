"""
Navigation Bar Component - Top Navigation Interface

This module renders the main navigation bar at the top of the application:
- F1 Pulse logo with car emoji
- Live countdown timer to next race event
- Navigation buttons (Home, Drivers, Constructors, Race Analytics)
- Responsive layout with Streamlit columns
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

from core.data_loader import get_schedule
from core.config import get_flag_url

def nav_to(page_path):
    """
    Navigate to a specific page in the Streamlit app.
    
    Args:
        page_path (str): The relative path to the page file (without extension).
                        Example: "home", "drivers", "race_analytics"
    
    Output: Uses st.switch_page() to navigate to pages/{page_path}.py
    """
    st.switch_page(f"pages/{page_path}.py")

def render_navbar():
    """
    Renders the complete navigation bar with logo, live timer, and menu buttons.
    
    This function:
    - Applies CSS styling to primary buttons (custom red border, hover effects)
    - Creates a responsive 6-column layout
    - Fetches and displays the next upcoming race with countdown timer
    - Provides navigation buttons for all main pages
    
    Output: Displays the navbar UI elements and injects CSS styling into the page.
    """
    # ==========================================
    # CSS STYLING FOR NAVIGATION BAR
    # ==========================================
    st.markdown("""
        <style>
            /* Primary Button Styling - Custom red border button design */
            [data-testid="stBaseButton-primary"] {
                background-color: transparent !important;          /* Transparent background */
                border: 1px solid #ff4b4b !important;              /* Red border (#ff4b4b = Streamlit red) */
                color: #ff4b4b !important;                         /* Red text color */
                border-radius: 20px !important;                    /* Rounded corners */
                padding: 0px 15px !important;                      /* Horizontal padding */
                font-size: 0.85rem !important;                     /* Slightly smaller font */
                height: 32px !important;                           /* Fixed height */
                min-height: 32px !important;                       /* Minimum height constraint */
                font-weight: bold !important;                      /* Bold text */
                transition: all 0.2s ease-in-out !important;       /* Smooth animation on hover */
            }
            
            /* Primary Button Hover State */
            [data-testid="stBaseButton-primary"]:hover { 
                background-color: rgba(255, 75, 75, 0.1) !important;   /* Light red background on hover */
                transform: translateY(-2px) !important;                  /* Slight upward movement on hover */
            }
            
            /* Hide the sidebar completely */
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)

    # ==========================================
    # TOP NAVIGATION BAR LAYOUT
    # ==========================================
    # Column layout: Logo | Timer | Button1 | Button2 | Button3 | Button4
    col_logo, col_next, col_n1, col_n2, col_n3, col_n4 = st.columns([0.9, 1.3, 1.0, 1.0, 1.0, 1.0], vertical_alignment="center")
    
    # Column 1: F1 Pulse Logo
    with col_logo:
        st.markdown("""
            <div style="display: flex; align-items: center;">
                <span style="font-size: 2rem; margin-right: 12px; line-height: 1;">🏎️</span>
                <div style="display: flex; flex-direction: column;">
                    <span style="font-size: 1.3rem; font-weight: 900; letter-spacing: 1px; color: #ffffff; line-height: 1;">F1 PULSE</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    # Column 2: Live Event Timer
    with col_next:
        now = datetime.now()
        schedule = get_schedule(now.year)
        
        if schedule is not None and not schedule.empty and 'EventDate' in schedule.columns:
            # Find future events starting from current time
            future_events = schedule[schedule['EventDate'].dt.tz_localize(None) > now]
            
            if not future_events.empty:
                # Get the next upcoming event
                next_event = future_events.iloc[0]
                country = str(next_event['Country'])
                event_name = str(next_event['EventName'])
                event_date = next_event['EventDate'].tz_localize(None)
                flag_url = get_flag_url(country)
                
                # Calculate time remaining in seconds
                diff_seconds = (event_date - now).total_seconds()
                
                # HTML/CSS/JavaScript for live countdown timer
                live_timer_html = f"""
                <style>
                    /* Timer Container Styling */
                    body {{
                        margin: 0; padding: 0; font-family: "Source Sans Pro", sans-serif;
                        background-color: transparent; color: white; overflow: hidden;
                    }}
                    
                    /* Main Timer Box */
                    .box {{
                        display: flex; align-items: center; background: rgba(255,255,255,0.05);
                        padding: 4px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);
                        height: 35px;
                    }}
                    
                    /* Country Flag Image */
                    .flag {{ 
                        height: 20px; border-radius: 3px; margin-right: 12px; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.5);
                    }}
                    
                    /* Event Info Section (Country + Event Name) */
                    .info {{
                        display: flex; flex-direction: column; justify-content: center;
                        margin-right: 15px; border-right: 1px solid rgba(255,255,255,0.1);
                        padding-right: 15px; flex-grow: 1; overflow: hidden; white-space: nowrap;
                    }}
                    
                    /* "Next Session" Label */
                    .label {{ 
                        font-size: 0.65rem; color: #a0a0a0; 
                        text-transform: uppercase; letter-spacing: 1px; line-height: 1.2; 
                    }}
                    
                    /* Event Name Display */
                    .val-name {{ 
                        font-size: 0.85rem; font-weight: bold; color: #ffffff; 
                        line-height: 1.2; text-overflow: ellipsis; overflow: hidden; 
                    }}
                    
                    /* Countdown Timer Display */
                    .val-time {{ 
                        font-size: 0.95rem; font-weight: 900; color: #ff4b4b; 
                        font-family: monospace; line-height: 1.2; white-space: nowrap; 
                    }}
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
                    // Calculate target time by adding seconds offset to current client time
                    var targetTime = new Date().getTime() + ({diff_seconds} * 1000);
                    
                    // Update timer display every second
                    function updateTimer() {{
                        var now = new Date().getTime();
                        var distance = targetTime - now;
                        
                        // If time has passed, show "LIVE"
                        if (distance < 0) {{
                            document.getElementById("live-timer").innerHTML = "LIVE";
                            return;
                        }}
                        
                        // Calculate days, hours, minutes, seconds
                        var d = Math.floor(distance / (1000 * 60 * 60 * 24));
                        var h = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                        var m = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                        var s = Math.floor((distance % (1000 * 60)) / 1000);
                        
                        // Display countdown in format: Xd Xh Xm Xs
                        document.getElementById("live-timer").innerHTML = d + "d " + h + "h " + m + "m " + s + "s";
                    }}
                    
                    // Update every second and run immediately
                    setInterval(updateTimer, 1000);
                    updateTimer();
                </script>
                """
                
                components.html(live_timer_html, height=45)
                
            else:
                # No more events this season
                st.markdown("<div style='height: 45px; display: flex; align-items: center; color: #888;'>Season Completed</div>", unsafe_allow_html=True)
        else:
            # Schedule data unavailable
            st.markdown("<div style='height: 45px; display: flex; align-items: center; color: #888;'>Schedule Unavailable</div>", unsafe_allow_html=True)
            
    # Column 3: Home Button
    with col_n1:
        if st.button("Home", type="primary", use_container_width=True): 
            nav_to("home")
    
    # Column 4: Drivers Button
    with col_n2:
        if st.button("Drivers", type="primary", use_container_width=True): 
            nav_to("drivers")
    
    # Column 5: Constructors Button
    with col_n3:
        if st.button("Constructors", type="primary", use_container_width=True): 
            nav_to("constructors")
    
    # Column 6: Race Analytics Button
    with col_n4:
        if st.button("Race Analytics", type="primary", use_container_width=True): 
            nav_to("race_analytics")

    # Horizontal separator line
    st.markdown("<hr style='margin: 5px 0 15px 0; border-color: rgba(255,255,255,0.1);'>", unsafe_allow_html=True)