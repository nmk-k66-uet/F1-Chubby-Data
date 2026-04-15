import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

@st.fragment
def fragment_strategy(session):
    """
    Hiển thị tab Chiến thuật (Strategy) bao gồm:
    - Biểu đồ dòng thời gian sử dụng lốp (Tire Strategy Timeline).
    - Phân tích chi tiết từng stint (Stint Performance Analysis) bao gồm độ mòn lốp và tính ổn định.
    """
    sub_overview, sub_stint = st.tabs(["📊 Strategy Overview", "📋 Stint Detail Analysis"])
    
    # Tiền xử lý dữ liệu laps để lấy thông tin stint và lốp
    all_laps = session.laps.copy().dropna(subset=['Stint', 'Compound'])
    compound_colors = {
        'SOFT': '#FF3333', 
        'MEDIUM': '#FFF200', 
        'HARD': '#FFFFFF', 
        'INTERMEDIATE': '#39B54A', 
        'WET': '#00AEEF'
    }

    # 1. BIỂU ĐỒ TỔNG QUAN CHIẾN THUẬT LỐP
    with sub_overview:
        st.subheader("Tire Strategy Timeline")
        finish_order = session.results['Abbreviation'].dropna().tolist()
        
        if not all_laps.empty:
            stints = all_laps.groupby(['Driver', 'Stint', 'Compound']).agg(
                StartLap=('LapNumber', 'min'), 
                EndLap=('LapNumber', 'max'), 
                StintLength=('LapNumber', 'count')
            ).reset_index()
            
            # Sắp xếp thứ tự các tay đua trên biểu đồ theo kết quả về đích
            stints['Driver'] = pd.Categorical(stints['Driver'], categories=finish_order, ordered=True)
            
            fig_strat = px.bar(
                stints.sort_values(['Driver', 'Stint']), 
                x='StintLength', 
                y='Driver', 
                color='Compound', 
                color_discrete_map=compound_colors, 
                orientation='h', 
                labels={'Driver': 'Driver', 'StintLength': 'Laps'}
            )
            
            fig_strat.update_layout(
                yaxis=dict(autorange="reversed"), 
                xaxis_title="Lap", 
                height=max(500, len(finish_order) * 30)
            )
            st.plotly_chart(fig_strat, width='stretch')
        else:
            st.info("Không có dữ liệu chiến thuật lốp cho phiên này.")

    # 2. PHÂN TÍCH CHI TIẾT TỪNG STINT
    with sub_stint:
        st.subheader("Stint Performance Analysis")
        stint_stats = []
        
        for (driver, stint, compound), group in all_laps.groupby(['Driver', 'Stint', 'Compound']):
            valid = group.dropna(subset=['LapTime'])
            fastest, avg, sigma, deg = "N/A", "N/A", "N/A", "N/A"
            
            if not valid.empty:
                fast_sec = valid['LapTime'].min().total_seconds()
                fastest = f"{int(fast_sec // 60):02d}:{fast_sec % 60:06.3f}"
                
                avg_sec = valid['LapTime'].mean().total_seconds()
                avg = f"{int(avg_sec // 60):02d}:{avg_sec % 60:06.3f}"
                
                l_sec = valid['LapTime'].dt.total_seconds()
                
                # Tính độ ổn định (Consistency) bằng độ lệch chuẩn, loại bỏ các lap bất thường (outlier > 105%)
                if len(l_sec) > 1: 
                    filtered_lsec = l_sec[l_sec <= l_sec.min() * 1.05]
                    sigma = f"σ = {filtered_lsec.std(ddof=0):.3f}s"
                    
                # Tính độ mòn lốp (Degradation) bằng hồi quy tuyến tính
                if len(valid.dropna(subset=['TyreLife'])) > 2:
                    try: 
                        deg = f"{np.polyfit(valid['TyreLife'], l_sec, 1)[0]:+.3f} s/lap"
                    except: 
                        pass
                        
            stint_stats.append({
                'Driver': driver, 
                'Stint': int(stint), 
                'Compound': compound, 
                'Length': f"{len(group)} (L{int(group['LapNumber'].min())}-L{int(group['LapNumber'].max())})", 
                'Fastest': fastest, 
                'Average': avg, 
                'Consistency': sigma, 
                'Degradation': deg
            })
            
        if stint_stats:
            stint_df = pd.DataFrame(stint_stats).sort_values(['Driver', 'Stint'])
            st.dataframe(stint_df, width='stretch', hide_index=True)
        else:
            st.info("Không có dữ liệu phân tích chi tiết stint.")

@st.fragment
def fragment_practice_strategy(session):
    """
    Hiển thị tab Chiến thuật (Strategy) thu gọn cho Practice.
    """
    sub_overview, sub_stint = st.tabs(["📊 Strategy Overview", "📋 Stint Detail Analysis"])
    
    all_laps = session.laps.copy().dropna(subset=['Stint', 'Compound'])
    compound_colors = {
        'SOFT': '#FF3333', 'MEDIUM': '#FFF200', 'HARD': '#FFFFFF', 
        'INTERMEDIATE': '#39B54A', 'WET': '#00AEEF'
    }

    with sub_overview:
        st.subheader("Practice Tire Timeline")
        finish_order = session.results['Abbreviation'].dropna().tolist()
        
        if not all_laps.empty:
            stints = all_laps.groupby(['Driver', 'Stint', 'Compound']).agg(
                StartLap=('LapNumber', 'min'), 
                EndLap=('LapNumber', 'max'), 
                StintLength=('LapNumber', 'count')
            ).reset_index()
            
            stints['Driver'] = pd.Categorical(stints['Driver'], categories=finish_order, ordered=True)
            fig_strat = px.bar(
                stints.sort_values(['Driver', 'Stint']), 
                x='StintLength', y='Driver', color='Compound', 
                color_discrete_map=compound_colors, orientation='h', 
                labels={'Driver': 'Driver', 'StintLength': 'Laps'}
            )
            fig_strat.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Lap", height=max(500, len(finish_order) * 30))
            st.plotly_chart(fig_strat, width='stretch')
        else:
            st.info("Không có dữ liệu lốp cho phiên này.")

    with sub_stint:
        st.subheader("Practice Long Run Analysis")
        stint_stats = []
        
        for (driver, stint, compound), group in all_laps.groupby(['Driver', 'Stint', 'Compound']):
            valid = group.dropna(subset=['LapTime'])
            fastest, avg = "N/A", "N/A"
            
            if not valid.empty:
                fast_sec = valid['LapTime'].min().total_seconds()
                fastest = f"{int(fast_sec // 60):02d}:{fast_sec % 60:06.3f}"
                avg_sec = valid['LapTime'].mean().total_seconds()
                avg = f"{int(avg_sec // 60):02d}:{avg_sec % 60:06.3f}"
                        
            stint_stats.append({
                'Driver': driver, 
                'Stint': int(stint), 
                'Compound': compound, 
                'Length': f"{len(group)} (L{int(group['LapNumber'].min())}-L{int(group['LapNumber'].max())})", 
                'Fastest': fastest, 
                'Average': avg
            })
            
        if stint_stats:
            stint_df = pd.DataFrame(stint_stats).sort_values(['Driver', 'Stint'])
            st.dataframe(stint_df, width='stretch', hide_index=True)
        else:
            st.info("Không có dữ liệu phân tích chi tiết stint.")