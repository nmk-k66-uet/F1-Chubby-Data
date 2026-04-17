import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from components.tab_race_control import fragment_race_control

@st.fragment
def fragment_positions(session, drivers, session_name):
    """
    Hiển thị tab phân tích Vị trí (Positions) bao gồm:
    - Biểu đồ thay đổi vị trí qua từng vòng
    - Bảng thông báo từ Race Control
    - Phân tích vị trí đạt được/đánh mất (Gained/Lost)
    """
    sub_chart, sub_rc, sub_analysis = st.tabs(["Position Chart", "Race Control", "Analysis"])
    
    if "sel_all_pos" not in st.session_state:
        st.session_state["sel_all_pos"] = True

    # 1. BIỂU ĐỒ VỊ TRÍ
    with sub_chart:
        col_title, col_filter = st.columns([3, 1])
        with col_title:
            st.subheader(f"Lap-by-Lap Position Changes - {session_name}")
            st.caption("Note: Within a team, the second driver is shown with a dashed line.")
        with col_filter:
            with st.expander("Filter Drivers", expanded=False):
                for drv in drivers:
                    if f"ch_{drv}" not in st.session_state: 
                        st.session_state[f"ch_{drv}"] = True
                        
                def toggle_all():
                    master_val = st.session_state["sel_all_pos"]
                    for d in drivers: 
                        st.session_state[f"ch_{d}"] = master_val
                        
                st.checkbox("Select All", value=True, key="sel_all_pos", on_change=toggle_all)
                selected_drivers = [drv for drv in drivers if st.checkbox(drv, key=f"ch_{drv}")]

        if not selected_drivers: 
            st.warning("Please select at least one driver to view data.")
        else:
            fig_pos = go.Figure()
            all_laps = session.laps
            team_count = {}
            for drv in selected_drivers:
                drv_laps = all_laps.pick_drivers(drv).dropna(subset=['Position'])
                if not drv_laps.empty:
                    driver_info = session.get_driver(drv)
                    team_name = driver_info['TeamName']
                    color = f"#{driver_info['TeamColor']}"
                    if color == "#nan" or not color: 
                        color = "white"
                    line_style = 'solid' if team_name not in team_count else 'dash'
                    team_count[team_name] = 1
                    
                    fig_pos.add_trace(go.Scatter(
                        x=drv_laps['LapNumber'], 
                        y=drv_laps['Position'], 
                        mode='lines', 
                        name=drv, 
                        line=dict(color=color, width=2.5, dash=line_style), 
                        hovertemplate=f"<b>{drv}</b> ({team_name})<br>Lap: %{{x}}<br>Pos: P%{{y}}<extra></extra>"
                    ))

            max_lap = int(all_laps['LapNumber'].max()) if not all_laps.empty else 50
            fig_pos.update_layout(
                yaxis=dict(autorange="reversed", tickmode='linear', dtick=1), 
                xaxis=dict(title="Lap", range=[1, max_lap], tickmode='linear', tick0=1, dtick=5, showgrid=True, gridcolor="rgba(255,255,255,0.1)"), 
                hovermode="x unified", 
                height=550, 
                plot_bgcolor="rgba(0,0,0,0)", 
                paper_bgcolor="rgba(0,0,0,0)", 
                margin=dict(l=0, r=0, t=40, b=80), 
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_pos, width='stretch')

    # 2. BẢNG RACE CONTROL
    with sub_rc:
        fragment_race_control(session)

    # 3. PHÂN TÍCH VỊ TRÍ (GAINED/LOST)
    with sub_analysis:
        st.subheader("Places Gained/Lost Summary")
        analysis_data = []
        for _, row in session.results.iterrows():
            pos, grid = pd.to_numeric(row['Position'], errors='coerce'), pd.to_numeric(row['GridPosition'], errors='coerce')
            change = f"↑ +{int(grid-pos)}" if grid > pos else (f"↓ {int(grid-pos)}" if grid < pos else "- 0")
            if grid == 0: 
                change = "Pit Start"
            
            analysis_data.append({
                'Final Pos': str(int(pos)) if pd.notna(pos) else "N/A", 
                'Driver': row['FullName'], 
                'Team': row['TeamName'], 
                'Grid': str(int(grid)) if grid > 0 else "Pit", 
                'Change': change, 
                'Status': row['Status']
            })

        def toggle_all():
        # Sử dụng .get() để lấy giá trị an toàn, mặc định là True nếu không tìm thấy
            master_val = st.session_state.get("sel_all_pos", True)
               
        def style_change(val): 
            return 'color: #00cc66; font-weight: bold;' if '↑' in str(val) else ('color: #ff4b4b; font-weight: bold;' if '↓' in str(val) else 'color: gray;')
            
        st.dataframe(pd.DataFrame(analysis_data).style.map(style_change, subset=['Change']), width='stretch', hide_index=True)