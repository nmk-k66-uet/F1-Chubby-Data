import streamlit as st
import plotly.graph_objects as go

@st.fragment
def fragment_lap_times(session, drivers):
    """
    Hiển thị tab Phân tích Thời gian vòng chạy (Lap Times) bao gồm:
    - Biểu đồ so sánh thời gian qua từng vòng giữa các tay đua.
    - Cấu trúc quản lý state để thêm/bớt linh hoạt các tay đua cần so sánh (tối đa 6 tay đua).
    """
    # Khởi tạo Session State cho việc quản lý các ô chọn tay đua
    if 'lt_boxes' not in st.session_state: 
        st.session_state['lt_boxes'] = ['box_0', 'box_1'] 
    if 'lt_box_counter' not in st.session_state: 
        st.session_state['lt_box_counter'] = 2
        
    boxes = st.session_state['lt_boxes']
    n = len(boxes)
    
    # Header và Nút thêm tay đua
    c_title, c_add = st.columns([4, 1])
    with c_title: 
        st.subheader("Lap Time Comparison")
    
    def add_driver():
        st.session_state['lt_boxes'].append(f"box_{st.session_state['lt_box_counter']}")
        st.session_state['lt_box_counter'] += 1
        
    with c_add:
        st.button("➕ Add Driver", disabled=n >= 6, width='stretch', on_click=add_driver)

    sel_drivers = []
    
    # Xây dựng lưới (grid) linh hoạt với tối đa 3 cột trên 1 hàng
    for i in range(0, n, 3):
        cols = st.columns(3)
        for j in range(3):
            idx = i + j
            if idx < n:
                b_id = boxes[idx]
                with cols[j]:
                    # Nếu có từ 3 tay đua trở lên, hiện nút "✖" (xóa) bên cạnh
                    if n >= 3:
                        sc1, sc2 = st.columns([4, 1])
                        with sc1: 
                            drv = st.selectbox("Driver", drivers, index=idx % len(drivers), key=f"sel_{b_id}", label_visibility="collapsed")
                        with sc2: 
                            def remove_driver(box_id=b_id):
                                st.session_state['lt_boxes'].remove(box_id)
                            st.button("✖", key=f"del_{b_id}", on_click=remove_driver)
                    else: 
                        drv = st.selectbox("Driver", drivers, index=idx % len(drivers), key=f"sel_{b_id}", label_visibility="collapsed")
                    
                    sel_drivers.append(drv)

    # Loại bỏ các lựa chọn trùng lặp
    unique_drv = list(dict.fromkeys(sel_drivers))
    
    # Vẽ biểu đồ Line so sánh thời gian
    if unique_drv:
        fig_l = go.Figure()
        for drv in unique_drv:
            d_laps = session.laps.pick_drivers(drv).dropna(subset=['LapTime'])
            if not d_laps.empty:
                # Lấy màu xe của tay đua
                drv_info = session.get_driver(drv)
                c = f"#{drv_info['TeamColor']}" if str(drv_info['TeamColor']) != 'nan' else 'white'
                
                fig_l.add_trace(go.Scatter(
                    x=d_laps['LapNumber'], 
                    y=d_laps['LapTime'].dt.total_seconds(), 
                    mode='lines+markers', 
                    name=drv, 
                    line=dict(color=c, width=2, shape='spline')
                ))
                
        fig_l.update_layout(
            xaxis_title="Lap", 
            yaxis_title="Time (s)", 
            hovermode="x unified", 
            height=600,
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_l, width='stretch')