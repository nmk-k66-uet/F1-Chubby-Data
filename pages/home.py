import streamlit as st
import pandas as pd
from datetime import datetime

# Import từ thư mục core
from core.config import get_flag_url
from core.data_loader import get_schedule, get_race_winner

def render():
    col_title, col_sel = st.columns([3, 1])
    with col_title:
        st.title("🏎️ F1 Pulse")
        st.markdown("Explore race schedules, results, and in-depth performance analysis.")
        
    with col_sel:
        st.markdown("<br>", unsafe_allow_html=True)
        # Quản lý state cho năm được chọn
        if 'selected_year' not in st.session_state:
            st.session_state['selected_year'] = 2026
            
        years_list = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        selected_year = st.selectbox("📅 Select Season:", years_list, index=years_list.index(st.session_state['selected_year']), label_visibility="collapsed")
        st.session_state['selected_year'] = selected_year

    st.divider()
    events_df = get_schedule(selected_year)

    if not events_df.empty:
        st.subheader(f"Race Calendar & Results - Season {selected_year}")
        
        # Vẽ lưới các thẻ (cards) sự kiện
        for i in range(0, len(events_df), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(events_df):
                    event = events_df.iloc[i + j]
                    col = cols[j]
                    
                    round_num = event['RoundNumber']
                    event_name = event['EventName']
                    country = event['Country']
                    flag_url = get_flag_url(country)
                    
                    event_date = event['EventDate']
                    if pd.notna(event_date):
                        date_str = event_date.strftime("%d %b, %Y")
                        is_completed = event_date.tz_localize(None) < datetime.now()
                    else:
                        date_str = "TBA"
                        is_completed = False
                    
                    format_type = event.get('EventFormat', 'conventional').capitalize()
                    
                    with col:
                        with st.container(border=True):
                            st.markdown(f"<h4 style='margin-bottom:0;'><img src='{flag_url}' width='32' style='border-radius:4px; vertical-align:middle; margin-right:10px; box-shadow: 0 0 2px rgba(255,255,255,0.3);'> Round {round_num}</h4>", unsafe_allow_html=True)
                            st.markdown(f"**{event_name}**")
                            st.caption(f"📍 {event['Location']}, {country} | 🗓️ {date_str}")
                            st.divider()
                            
                            if is_completed:
                                st.markdown("🟢 **Status:** Completed")
                                winner = get_race_winner(selected_year, round_num)
                                st.markdown(f"🏆 **Winner:** {winner}")
                            else:
                                st.markdown("⏳ **Status:** Upcoming")
                                if format_type in ['Sprint', 'Sprint_qualifying']: 
                                    st.markdown("🏎️ **Format:** Sprint Weekend")
                                else: 
                                    st.markdown("🏎️ **Format:** Conventional")
                            
                            if st.button(f"Analyze", key=f"btn_{selected_year}_{round_num}", width='stretch', disabled=not is_completed):
                                st.session_state['selected_event'] = {'year': selected_year, 'round': round_num, 'name': event_name, 'country': country}
                                st.switch_page("pages/details.py")
    else:
        st.warning("No schedule data found for this season.")

# Gọi hàm render khi file được chạy
render()