import streamlit as st
import pandas as pd
import plotly.graph_objects as go

@st.fragment
def fragment_telemetry_card(session, drivers, chart_info, idx):
    """
    Hiển thị một thẻ biểu đồ (Card) telemetry đơn lẻ.
    Được đánh dấu @st.fragment để khi người dùng thay đổi Driver/Lap ở 1 thẻ, 
    chỉ thẻ đó tải lại dữ liệu chứ không tải lại toàn bộ tab.
    """
    gear_colors = {1: '#00FFFF', 2: '#FF7F50', 3: '#008080', 4: '#FF0000', 5: '#FF1493', 6: '#0000CD', 7: '#ADFF2F', 8: '#FFD700'}
    
    with st.container(border=True):
        c_title, c_drv, c_lap = st.columns([2, 1, 1])
        
        # Chọn tay đua
        with c_drv: 
            drv_sel = st.selectbox("Drv", drivers, key=f"tel_drv_{idx}", label_visibility="collapsed")
            
        # Chọn vòng chạy
        with c_lap:
            laps_list = session.laps.pick_drivers(drv_sel)['LapNumber'].dropna().astype(int).tolist()
            lap_sel = st.selectbox("Lap", ["Fastest"] + [f"Lap {l}" for l in laps_list], key=f"tel_lap_{idx}", label_visibility="collapsed")

        # Hiển thị Title cho Card
        lap_str_title = "Fastest Lap" if lap_sel == "Fastest" else lap_sel
        with c_title:
            st.markdown(f"<div style='font-weight:bold; font-size:1.1rem; padding-top:2px; line-height:1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{drv_sel}'s {lap_str_title}<br><span style='color:#00cc66; font-size:0.9rem; letter-spacing: 0.5px;'>{chart_info['title'].upper()}</span></div>", unsafe_allow_html=True)
            
        try:
            drv_laps = session.laps.pick_drivers(drv_sel)
            lap_data = drv_laps.pick_fastest() if lap_sel == "Fastest" else drv_laps[drv_laps['LapNumber'] == int(lap_sel.replace("Lap ", ""))].iloc[0]
            
            if pd.isna(lap_data['LapTime']): 
                st.warning("No telemetry data available.")
            else:
                tel = lap_data.get_telemetry().copy()
                drv_color = f"#{session.get_driver(drv_sel)['TeamColor']}" if str(session.get_driver(drv_sel)['TeamColor']) != 'nan' else 'white'
                fig = go.Figure()
                
                # --- Xử lý biểu đồ MAP (Gear Shifts) ---
                if chart_info['type'] == 'map':
                    tel['nGear'] = pd.to_numeric(tel['nGear'], errors='coerce').fillna(0).astype(int)
                    
                    # Vẽ điểm trống để tạo Legend
                    for gear in range(1, 9): 
                        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color=gear_colors.get(gear, '#FFFFFF')), name=f"Gear {gear}", showlegend=True))
                        
                    tel['Block'] = (tel['nGear'] != tel['nGear'].shift(1)).cumsum()
                    block_ids = tel['Block'].unique()
                    
                    for k, b in enumerate(block_ids):
                        group = tel[tel['Block'] == b].copy()
                        if k < len(block_ids) - 1: 
                            group = pd.concat([group, tel[tel['Block'] == block_ids[k+1]].iloc[0:1]], ignore_index=True)
                            
                        gear = int(group['nGear'].iloc[0])
                        fig.add_trace(go.Scatter(x=group['X'], y=group['Y'], mode='lines', line=dict(color=gear_colors.get(gear, '#FFFFFF'), width=5), name=f"Gear {gear}", showlegend=False, hoverinfo='skip'))
                        
                    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1), legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5, font=dict(size=11)))
                    
                # --- Xử lý biểu đồ LINE (Speed, Throttle, Brake...) ---
                else:
                    fig.add_trace(go.Scatter(
                        x=tel['Distance'], y=tel[chart_info['metric']], 
                        mode='lines', line=dict(color=drv_color, width=2.5), 
                        hovertemplate="Dist: %{x}m<br>Value: %{y}<extra></extra>"
                    ))
                    fig.update_layout(
                        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text="Distance (m)"), 
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title_text=chart_info['unit']), 
                        hovermode="x unified", showlegend=False
                    )
                    
                fig.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=15), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
                
        except Exception as e: 
            st.error(f"Error rendering chart: {str(e)}")

def render_telemetry_tab(session, drivers):
    """
    Hàm chính để render toàn bộ Tab Telemetry.
    Quản lý việc tạo lưới 2x3 cho 6 biểu đồ Telemetry.
    """
    st.subheader("Comprehensive Telemetry Analysis")
    st.divider()
    
    charts = [
        {'title': 'Speed Trace', 'metric': 'Speed', 'type': 'line', 'unit': 'km/h'},
        {'title': 'Gear Shifts', 'metric': 'nGear', 'type': 'map', 'unit': ''},
        {'title': 'Throttle Input', 'metric': 'Throttle', 'type': 'line', 'unit': '%'},
        {'title': 'Brake Input', 'metric': 'Brake', 'type': 'line', 'unit': ''},
        {'title': 'RPM', 'metric': 'RPM', 'type': 'line', 'unit': 'RPM'},
        {'title': 'DRS Usage', 'metric': 'DRS', 'type': 'line', 'unit': 'State'}
    ]
    
    # Tạo lưới 2 cột
    for i in range(0, 6, 2):
        cols = st.columns(2)
        for j in range(2):
            idx = i + j
            with cols[j]: 
                fragment_telemetry_card(session, drivers, charts[idx], idx)