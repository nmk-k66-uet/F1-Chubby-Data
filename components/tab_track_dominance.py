import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

@st.fragment
def fragment_dominance(session, drivers):
    """
    Renders the Track Dominance tab comparing two drivers' performance around the track.
    
    Features:
    - Track dominance map: Track divided into 50 mini-sectors, colored by fastest driver
    - Speed trace comparison: Line plot comparing speeds vs distance
    - Secondary metrics: Throttle, brake, RPM, and DRS comparison charts
    
    Args:
        session: FastF1 session object with telemetry data.
        drivers (list): List of driver abbreviations available in session.
    
    Output: Displays side-by-side comparison charts and track dominance visualization.
    
    Dominance Logic:
    - Yellow (Neutral): Speed difference <= 2 km/h
    - Driver 1 color (Faster): Driver 1 > Driver 2 speed
    - Driver 2 color (Faster): Driver 2 > Driver 1 speed
    """
    col_title, col_ctrls = st.columns([1.2, 2.8])
    with col_title:
        st.subheader("Track Dominance & Speed Trace")
        
    # --- PHẦN ĐIỀU KHIỂN (CONTROLS) ---
    with col_ctrls:
        c1, c2, c3, c4, c5 = st.columns([2, 2, 0.5, 2, 2])
        with c1: 
            drv1 = st.selectbox("Driver 1", drivers, index=0, key="dom_d1")
        with c2:
            laps1 = session.laps.pick_drivers(drv1)['LapNumber'].dropna().astype(int).tolist()
            sel_lap1 = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps1], index=0, key="dom_l1")
        with c3: 
            st.markdown("<div style='text-align: center; font-weight: bold; font-size: 1.2rem; margin-top: 35px;'>VS</div>", unsafe_allow_html=True)
        with c4: 
            drv2 = st.selectbox("Driver 2", drivers, index=1 if len(drivers) > 1 else 0, key="dom_d2")
        with c5:
            laps2 = session.laps.pick_drivers(drv2)['LapNumber'].dropna().astype(int).tolist()
            sel_lap2 = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps2], index=0, key="dom_l2")

    st.divider()
    
    # --- PHẦN XỬ LÝ VÀ VẼ BIỂU ĐỒ ---
    try:
        def get_lap_data(drv, sel):
            drv_laps = session.laps.pick_drivers(drv)
            if sel == "Fastest": 
                return drv_laps.pick_fastest()
            else: 
                return drv_laps[drv_laps['LapNumber'] == int(sel.replace("Lap ", ""))].iloc[0]

        lap1 = get_lap_data(drv1, sel_lap1)
        lap2 = get_lap_data(drv2, sel_lap2)
        
        if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']): 
            st.warning("Selected laps do not have valid telemetry data.")
        else:
            tel1 = lap1.get_telemetry()
            tel2 = lap2.get_telemetry()
            
            c1 = f"#{session.get_driver(drv1)['TeamColor']}" if str(session.get_driver(drv1)['TeamColor']) != 'nan' else 'white'
            c2 = f"#{session.get_driver(drv2)['TeamColor']}" if str(session.get_driver(drv2)['TeamColor']) != 'nan' else 'white'
            
            # Tránh trường hợp 2 xe cùng đội (cùng màu) khiến biểu đồ không thể phân biệt
            if c1 == c2: 
                c2 = "#00FFFF" 
                
            # Chia đường đua thành 50 Mini-sectors
            num_sectors = 50
            max_dist = max(tel1['Distance'].max(), tel2['Distance'].max())
            sector_length = max_dist / num_sectors
            
            tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
            tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)
            
            sectors = pd.DataFrame({
                'S1': tel1.groupby('MiniSector')['Speed'].mean(), 
                'S2': tel2.groupby('MiniSector')['Speed'].mean()
            }).fillna(0)
            
            # Đánh giá xem ai nhanh hơn ở từng sector (chênh lệch <= 2km/h coi như Neutral)
            conditions = [abs(sectors['S1'] - sectors['S2']) <= 2.0, sectors['S1'] > sectors['S2']]
            sectors['Dominant'] = np.select(conditions, [0, 1], default=2)
            tel1['Dominant'] = tel1['MiniSector'].map(sectors['Dominant'])
            
            col_map, col_speed = st.columns(2)
            
            # 1. BẢN ĐỒ TRACK DOMINANCE
            with col_map:
                fig_map = go.Figure()
                
                # Gộp các điểm liên tiếp có cùng người thống trị (Dominant) thành một Block để vẽ nét liền
                tel1['Block'] = (tel1['Dominant'] != tel1['Dominant'].shift(1)).cumsum()
                block_ids = tel1['Block'].unique()
                show_leg1, show_leg2, show_leg0 = True, True, True
                
                for i, b in enumerate(block_ids):
                    group = tel1[tel1['Block'] == b].copy()
                    
                    # Nối điểm cuối của block hiện tại với điểm đầu của block tiếp theo để không bị đứt đoạn
                    if i < len(block_ids) - 1: 
                        group = pd.concat([group, tel1[tel1['Block'] == block_ids[i+1]].iloc[0:1]])
                        
                    dom_val = group['Dominant'].iloc[0]
                    color, drv_name = ("#FFFF00", "Neutral") if dom_val == 0 else (c1, f"{drv1} Faster") if dom_val == 1 else (c2, f"{drv2} Faster")
                    
                    # Chỉ hiện Legend 1 lần cho mỗi trạng thái
                    show_leg = False
                    if dom_val == 1 and show_leg1: show_leg = True; show_leg1 = False
                    elif dom_val == 2 and show_leg2: show_leg = True; show_leg2 = False
                    elif dom_val == 0 and show_leg0: show_leg = True; show_leg0 = False
                    
                    fig_map.add_trace(go.Scatter(
                        x=group['X'], y=group['Y'], 
                        mode='lines', 
                        line=dict(color=color, width=8), 
                        name=drv_name, 
                        showlegend=show_leg, 
                        hoverinfo='skip'
                    ))
                    
                fig_map.update_layout(
                    title="Track Dominance Map", 
                    xaxis=dict(visible=False), 
                    yaxis=dict(visible=False, scaleanchor="x", scaleratio=1), 
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    margin=dict(l=0, r=0, t=40, b=60), 
                    legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_map, width='stretch')
                
            # 2. BIỂU ĐỒ SPEED TRACE
            with col_speed:
                fig_speed = go.Figure()
                fig_speed.add_trace(go.Scatter(
                    x=tel1['Distance'], y=tel1['Speed'], 
                    mode='lines', name=f"{drv1} ({sel_lap1})", 
                    line=dict(color=c1, width=2)
                ))
                fig_speed.add_trace(go.Scatter(
                    x=tel2['Distance'], y=tel2['Speed'], 
                    mode='lines', name=f"{drv2} ({sel_lap2})", 
                    line=dict(color=c2, width=2)
                ))
                fig_speed.update_layout(
                    title="Speed Trace", 
                    xaxis_title="Distance (m)", 
                    yaxis_title="Speed (km/h)", 
                    hovermode="x unified", 
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    margin=dict(l=0, r=0, t=40, b=60), 
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"), 
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"), 
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_speed, width='stretch')

            st.divider()
            
            # 3. CÁC BIỂU ĐỒ SO SÁNH TELEMETRY BỔ SUNG
            st.subheader("Additional Telemetry Comparison")
            
            metrics = [('Throttle (%)', 'Throttle'), ('Brake', 'Brake'), ('RPM', 'RPM'), ('DRS', 'DRS')]
            for i in range(0, 4, 2):
                cols = st.columns(2)
                for j in range(2):
                    metric_title, metric_col = metrics[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            fig_ind = go.Figure()
                            fig_ind.add_trace(go.Scatter(
                                x=tel1['Distance'], y=tel1[metric_col], 
                                mode='lines', line=dict(color=c1, width=2), name=f"{drv1}"
                            ))
                            fig_ind.add_trace(go.Scatter(
                                x=tel2['Distance'], y=tel2[metric_col], 
                                mode='lines', line=dict(color=c2, width=2), name=f"{drv2}"
                            ))
                            fig_ind.update_layout(
                                title=dict(text=f"<b>{metric_title} Comparison</b>", font=dict(size=16), x=0.02, y=0.95), 
                                legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5, font=dict(size=11), bgcolor="rgba(0,0,0,0)"), 
                                height=320, hovermode="x unified", 
                                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', 
                                margin=dict(l=0, r=0, t=45, b=60), 
                                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text="Distance (m)"), 
                                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)")
                            )
                            st.plotly_chart(fig_ind, width='stretch', config={'displaylogo': False})
                            
    except Exception as e: 
        st.error(f"Error processing telemetry data: {e}")