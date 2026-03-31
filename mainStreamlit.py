import streamlit as st
import fastf1
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# Cấu hình trang Streamlit
st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")
fastf1.Cache.enable_cache('f1_cache')

st.title("🏎️ F1 Pulse Dashboard - Interactive Analytics")

# --- Hàm tải dữ liệu ---
@st.cache_data(show_spinner=False)
def load_f1_session(year, gp, session_type):
    try:
        session = fastf1.get_session(year, gp, session_type)
        session.load(telemetry=True, weather=False)
        return session
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None

# --- SIDEBAR ĐIỀU KHIỂN ---
st.sidebar.header("Data Configuration")
selected_year = st.sidebar.selectbox("Season:", [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018], index=2)
selected_gp = st.sidebar.selectbox("Grand Prix:", ["Australia", "China", "Japan", "Bahrain", "Saudi Arabia", "Miami", "Emilia-Romagna", "Monaco", "Spain", "Canada", "Austria", "Great Britain", "Belgium", "Hungary", "Netherlands", "Italy", "Azerbaijan", "Singapore", "United States", "Mexico", "Brazil", "Las Vegas", "Qatar", "Abu Dhabi"], index=3)
selected_session = st.sidebar.selectbox("Session:", ["FP1", "FP2", "FP3", "Q", "S", "SS", "SQ", "R"], index=7)

if st.sidebar.button("Loading Data", type="primary"):
    with st.spinner(f"Loading data for {selected_gp} {selected_year} - {selected_session}..."):
        st.session_state['session'] = load_f1_session(selected_year, selected_gp, selected_session)

# --- XỬ LÝ KHI DỮ LIỆU ĐÃ ĐƯỢC TẢI ---
if 'session' in st.session_state and st.session_state['session'] is not None:
    session = st.session_state['session']
    st.success(f"Loaded: {session.event['EventName']} - {session.name}")
    
    drivers = session.results['Abbreviation'].dropna().tolist()
    
# --- TẠO CÁC TABS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overall Results", 
        "📈 Telemetry Analysis", 
        "🗺️ Race Track Map", 
        "⏱️ Strategy & Tires", 
        "🌬️ Aerodynamics (Aero)"
    ])

    # ==========================================
    # TAB 1: KẾT QUẢ
    # ==========================================
    with tab1:
        st.subheader("Overall Race Results")
        results_df = session.results[['Position', 'FullName', 'TeamName', 'Time']].copy()
        results_df['Time'] = results_df['Time'].apply(lambda x: str(x).split()[-1] if pd.notna(x) else "N/A")
        st.dataframe(results_df, use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 2: TELEMETRY (Giữ nguyên)
    # ==========================================
    with tab2:
        st.subheader("Telemetry Comparison")
        col1, col2 = st.columns(2)
        drv1 = col1.selectbox("Driver 1", drivers, index=0, key="tel_drv1")
        drv2 = col2.selectbox("Driver 2", drivers, index=1 if len(drivers) > 1 else 0, key="tel_drv2")

        if st.button("Plot Telemetry Chart"):
            try:
                lap_drv1 = session.laps.pick_drivers(drv1).pick_fastest()
                lap_drv2 = session.laps.pick_drivers(drv2).pick_fastest()

                tel_drv1 = lap_drv1.get_telemetry().add_distance()
                tel_drv2 = lap_drv2.get_telemetry().add_distance()

                color_drv1 = f"#{session.get_driver(drv1)['TeamColor']}"
                color_drv2 = f"#{session.get_driver(drv2)['TeamColor']}"
                if color_drv1 == "#nan" or not color_drv1: color_drv1 = "#ffffff"
                if color_drv2 == "#nan" or not color_drv2: color_drv2 = "#888888"

                fig_tel = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                        vertical_spacing=0.03,
                                        row_heights=[0.5, 0.15, 0.15, 0.2],
                                        subplot_titles=("Speed (km/h)", "Throttle (%)", "Brake", "Gear"))

                for drv, tel, color in zip([drv1, drv2], [tel_drv1, tel_drv2], [color_drv1, color_drv2]):
                    fig_tel.add_trace(go.Scatter(x=tel['Distance'], y=tel['Speed'], name=drv, line=dict(color=color), legendgroup=drv), row=1, col=1)
                    fig_tel.add_trace(go.Scatter(x=tel['Distance'], y=tel['Throttle'], name=drv, line=dict(color=color), showlegend=False, legendgroup=drv), row=2, col=1)
                    fig_tel.add_trace(go.Scatter(x=tel['Distance'], y=tel['Brake'], name=drv, line=dict(color=color), showlegend=False, legendgroup=drv), row=3, col=1)
                    fig_tel.add_trace(go.Scatter(x=tel['Distance'], y=tel['nGear'], name=drv, line=dict(color=color), showlegend=False, legendgroup=drv), row=4, col=1)

                fig_tel.update_layout(height=800, hovermode="x unified", title_text="Telemetry Comparison")
                fig_tel.update_xaxes(title_text="Distance (m)", row=4, col=1)
                
                st.plotly_chart(fig_tel, use_container_width=True)
            except Exception as e:
                st.error(f"Error plotting Telemetry chart: {e}")

    # ==========================================
    # TAB 3: TRACK MAP (Giữ nguyên)
    # ==========================================
    with tab3:
        st.subheader("Race Track Map & Corner Characteristics")
        col1, col2 = st.columns(2)
        track_drv = col1.selectbox("Select Driver:", drivers, key="track_drv")
        color_mode = col2.radio("Color the map by:", ["Speed", "Gear"], horizontal=True)

        if st.button("Plot Track Map"):
            try:
                lap = session.laps.pick_drivers(track_drv).pick_fastest()
                telemetry = lap.get_telemetry()
                
                hover_text = [f"Speed: {s} km/h<br>Gear: {g}" for s, g in zip(telemetry['Speed'], telemetry['nGear'])]

                if "Speed" in color_mode:
                    color_data = telemetry['Speed']
                    colorscale = 'Plasma'
                    cb_title = 'Speed (km/h)'
                else:
                    color_data = telemetry['nGear']
                    colorscale = 'Jet' 
                    cb_title = 'Gear'

                fig_track = go.Figure(data=go.Scatter(
                    x=telemetry['X'], y=telemetry['Y'], mode='markers',
                    marker=dict(size=6, color=color_data, colorscale=colorscale, showscale=True, colorbar=dict(title=cb_title)),
                    text=hover_text, hoverinfo='text'
                ))

                fig_track.update_yaxes(scaleanchor="x", scaleratio=1, showticklabels=False, showgrid=False, zeroline=False)
                fig_track.update_xaxes(showticklabels=False, showgrid=False, zeroline=False)
                fig_track.update_layout(height=700, title=f"{track_drv} Track Profile", plot_bgcolor="rgba(0,0,0,0)")

                st.plotly_chart(fig_track, use_container_width=True)
            except Exception as e:
                st.error(f"Error plotting Track Map: {e}")

    # ==========================================
    # TAB 4: STRATEGY (Giữ nguyên)
    # ==========================================
    with tab4:
        st.subheader("Strategy Analysis, Stability & Tire Wear")
        strategy_drv = st.selectbox("Select Driver (for tire analysis below):", drivers, key="strat_drv")

        if st.button("Analyze Strategy"):
            try:
                quick_laps = session.laps.pick_quicklaps()
                all_laps = session.laps
                
                all_drivers = quick_laps['Driver'].dropna().unique()
                driver_stats = []
                comp_map = {'SOFT': 'S', 'MEDIUM': 'M', 'HARD': 'H', 'INTERMEDIATE': 'I', 'WET': 'W'}

                for drv in all_drivers:
                    drv_laps = quick_laps.pick_drivers(drv)
                    times = drv_laps['LapTime'].dt.total_seconds().dropna()
                    
                    if not times.empty:
                        mean_time = times.mean()
                        drv_all_laps = all_laps.pick_drivers(drv)
                        compounds = drv_all_laps['Compound'].dropna().unique()
                        comp_seq = "-".join([comp_map.get(c, str(c)[0]) for c in compounds])
                        
                        driver_stats.append({'drv': drv, 'mean': mean_time, 'times': times, 'comp_seq': comp_seq})

                if driver_stats:
                    driver_stats.sort(key=lambda x: x['mean'])
                    best_mean = driver_stats[0]['mean']
                    fig_box = go.Figure()
                    
                    for stat in driver_stats:
                        drv = stat['drv']
                        mean_time = stat['mean']
                        diff = mean_time - best_mean
                        comp_seq = stat['comp_seq']
                        
                        diff_str = f"+{diff:.2f}" if diff > 0 else "+0.00"
                        label = f"<b>{drv}</b><br>{mean_time:.2f}<br>{diff_str}<br>{comp_seq}"
                        
                        color = f"#{session.get_driver(drv)['TeamColor']}"
                        if color == "#nan" or not color: color = "#555555"
                        
                        fig_box.add_trace(go.Box(
                            y=stat['times'], name=label, fillcolor=color, 
                            line=dict(color='white', width=1.5), 
                            marker=dict(color='white', symbol='circle-open', size=6, opacity=0.8), 
                            boxmean=True, boxpoints='outliers', showlegend=False
                        ))

                    fig_box.update_layout(
                        title="Global Racepace (Drivers Sorted by Mean Laptime)",
                        yaxis_title="Smoothed Laptime (s)", height=600, xaxis=dict(tickangle=0), 
                        margin=dict(b=90), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
                    )
                    
                    fig_box.add_annotation(text="<b>RACE PACE</b>", xref="paper", yref="paper", x=0.25, y=1.05, showarrow=False, font=dict(size=20, color="black"), bgcolor="yellow", borderpad=4)
                    explainer = ("Dashed Line: Mean, Solid Line: Median<br>Boxes contain 50% of the laps<br>Dots indicate outliers")
                    fig_box.add_annotation(text=explainer, xref="paper", yref="paper", x=0.99, y=0.01, xanchor="right", yanchor="bottom", showarrow=False, font=dict(size=11, color="white"), align="left", bgcolor="rgba(0,0,0,0.5)")

                    st.plotly_chart(fig_box, use_container_width=True)

                col1, col2 = st.columns(2)

                drv_laps_tyre = quick_laps.pick_drivers(strategy_drv).dropna(subset=['TyreLife', 'LapTime'])
                x = drv_laps_tyre['TyreLife']
                y = drv_laps_tyre['LapTime'].dt.total_seconds()
                
                fig_tyre = px.scatter(drv_laps_tyre, x='TyreLife', y=y, color='Compound', color_discrete_map={'SOFT': 'red', 'MEDIUM': 'yellow', 'HARD': 'white', 'INTERMEDIATE': 'green', 'WET': 'blue'}, title=f"Tyre Degradation - {strategy_drv}", trendline="ols")
                fig_tyre.update_layout(xaxis_title="Tyre Age (Laps)", yaxis_title="Lap Time (s)", height=450)
                col1.plotly_chart(fig_tyre, use_container_width=True)

                fig_gap = go.Figure()
                top_drivers = session.results['Abbreviation'].head(5).tolist() 
                leader = top_drivers[0]
                leader_laps = all_laps.pick_drivers(leader)[['LapNumber', 'Time']].set_index('LapNumber')
                
                for drv in top_drivers:
                    color = f"#{session.get_driver(drv)['TeamColor']}"
                    if color == "#nan" or not color: color = "white"
                    curr_drv_laps = all_laps.pick_drivers(drv)[['LapNumber', 'Time']].set_index('LapNumber')
                    merged = curr_drv_laps.join(leader_laps, lsuffix='_drv', rsuffix='_leader', how='inner')
                    gap = (merged['Time_drv'] - merged['Time_leader']).dt.total_seconds()
                    fig_gap.add_trace(go.Scatter(x=merged.index, y=gap, mode='lines', name=drv, line=dict(color=color, width=3)))

                fig_gap.update_layout(title="Race Trace (Gap to Leader)", xaxis_title="Lap Number", yaxis_title="Gap to Leader (Seconds)", yaxis=dict(autorange="reversed"), hovermode="x unified", height=450)
                col2.plotly_chart(fig_gap, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error plotting Strategy chart: {e}")

    # ==========================================
    # TAB 5: AERO (DOWNFORCE VS DRAG)
    # ==========================================
    with tab5:
        st.subheader("Aerodynamic Analysis (Top Speed vs Mean Speed)")
        st.info("Chart showing the fastest laps of each team to evaluate downforce and drag. Loading telemetry for all 10 teams may take several tens of seconds.")
        
        if st.button("Plot Aerodynamic Chart"):
            with st.spinner("Processing telemetry data for 10 teams..."):
                try:
                    # Lấy danh sách các đội đua trong phiên
                    teams = session.results['TeamName'].dropna().unique()
                    aero_data = []

                    for team in teams:
                        # Lấy tất cả vòng đua của đội này
                        team_laps = session.laps.pick_teams(team)
                        fastest_lap = team_laps.pick_fastest()
                        
                        if not pd.isnull(fastest_lap['LapTime']):
                            # Lấy driver tạo ra vòng nhanh nhất đó để lấy màu sắc chuẩn
                            driver = fastest_lap['Driver']
                            color = f"#{session.get_driver(driver)['TeamColor']}"
                            if color == "#nan" or not color: color = "#ffffff"

                            # Tải Telemetry
                            tel = fastest_lap.get_telemetry()
                            mean_speed = tel['Speed'].mean()
                            top_speed = tel['Speed'].max()

                            aero_data.append({
                                'Team': team,
                                'MeanSpeed': mean_speed,
                                'TopSpeed': top_speed,
                                'Color': color
                            })
                    
                    if aero_data:
                        df_aero = pd.DataFrame(aero_data)
                        
                        # Tính toán điểm giao cắt (Median) để chia 4 góc phần tư
                        mid_x = df_aero['MeanSpeed'].median()
                        mid_y = df_aero['TopSpeed'].median()

                        # Xác định giới hạn ngoài cùng của trục tọa độ
                        min_x, max_x = df_aero['MeanSpeed'].min() - 1, df_aero['MeanSpeed'].max() + 1
                        min_y, max_y = df_aero['TopSpeed'].min() - 2, df_aero['TopSpeed'].max() + 2
                        
                        # TÍNH TOÁN KHOẢNG LÙI (PADDING): Thu nhỏ các đường kẻ lại khoảng 5% so với viền đồ thị
                        pad_x = (max_x - min_x) * 0.1 
                        pad_y = (max_y - min_y) * 0.1
                        inner_min_x, inner_max_x = min_x + pad_x, max_x - pad_x
                        inner_min_y, inner_max_y = min_y + pad_y, max_y - pad_y

                        fig_aero = go.Figure()

                        # Vẽ các điểm Scatter (Các đội đua)
                        fig_aero.add_trace(go.Scatter(
                            x=df_aero['MeanSpeed'],
                            y=df_aero['TopSpeed'],
                            mode='markers+text',
                            text=df_aero['Team'],
                            textposition="top center",
                            marker=dict(size=18, color=df_aero['Color'], line=dict(width=2, color='white')),
                            textfont=dict(color=df_aero['Color'], size=12, weight='bold'),
                            showlegend=False
                        ))

                        # VẼ TRỤC THẬP TỰ PHÂN (Sử dụng tọa độ inner lùi vào trong để không chạm viền)
                        fig_aero.add_shape(type="line", x0=mid_x, y0=inner_min_y, x1=mid_x, y1=inner_max_y, line=dict(color="rgba(255, 255, 255, 0.4)", width=2))
                        fig_aero.add_shape(type="line", x0=inner_min_x, y0=mid_y, x1=inner_max_x, y1=mid_y, line=dict(color="rgba(255, 255, 255, 0.4)", width=2))

                        # VẼ CÁC ĐƯỜNG CHÉO (Cũng thu nhỏ lại bằng tọa độ inner)
                        fig_aero.add_shape(type="line", x0=mid_x, y0=mid_y, x1=inner_max_x, y1=inner_max_y, line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dash"))
                        fig_aero.add_shape(type="line", x0=mid_x, y0=mid_y, x1=inner_max_x, y1=inner_min_y, line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dash"))
                        fig_aero.add_shape(type="line", x0=mid_x, y0=mid_y, x1=inner_min_x, y1=inner_max_y, line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dash"))
                        fig_aero.add_shape(type="line", x0=mid_x, y0=mid_y, x1=inner_min_x, y1=inner_min_y, line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dash"))

                        # Thêm các nhãn text chú thích góc phần tư
                        annotations = [
                            # Labels trục ngang/dọc
                            dict(x=mid_x, y=max_y-0.75, text="Low Drag ▲", showarrow=False, font=dict(size=14, color="white"), yanchor="bottom"),
                            dict(x=mid_x, y=min_y+0.75, text="▼ High Drag", showarrow=False, font=dict(size=14, color="white"), yanchor="top"),
                            dict(x=max_x-0.75, y=mid_y, text="Quick ►", showarrow=False, font=dict(size=14, color="white"), xanchor="left"),
                            dict(x=min_x+0.75, y=mid_y, text="◄ Slow", showarrow=False, font=dict(size=14, color="white"), xanchor="right"),
                            
                            # Labels 4 góc phần tư
                            dict(x=inner_max_x, y=inner_max_y, text="Correlated with<br><b>High Efficiency</b>", showarrow=False, font=dict(size=12, color="gray"), xanchor="right", yanchor="top"),
                            dict(x=inner_max_x, y=inner_min_y, text="Correlated with<br><b>High Downforce</b>", showarrow=False, font=dict(size=12, color="gray"), xanchor="right", yanchor="bottom"),
                            dict(x=inner_min_x, y=inner_max_y, text="Correlated with<br><b>Low Downforce</b>", showarrow=False, font=dict(size=12, color="gray"), xanchor="left", yanchor="top"),
                            dict(x=inner_min_x, y=inner_min_y, text="Correlated with<br><b>Low Efficiency</b>", showarrow=False, font=dict(size=12, color="gray"), xanchor="left", yanchor="bottom"),
                        ]

                        fig_aero.update_layout(
                            title="Aerodynamic Performance: Top Speed vs Mean Speed (Best Lap of Each Team)",
                            xaxis_title="Mean Speed (km/h)",
                            yaxis_title="Top Speed (km/h)",
                            height=750,
                            annotations=annotations,
                            xaxis=dict(range=[min_x, max_x], showgrid=False),
                            yaxis=dict(range=[min_y, max_y], showgrid=False),
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)"
                        )

                        st.plotly_chart(fig_aero, use_container_width=True)
                    else:
                        st.warning("Not enough valid data to plot the chart.")
                except Exception as e:
                    st.error(f"Error plotting Aerodynamic chart: {e}")

else:
    st.info("👈 Please select a Season, Race, and Session from the sidebar and click 'Load Data' to get started.")