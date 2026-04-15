import streamlit as st
import pandas as pd

@st.fragment
def fragment_results(session, session_code, session_name):
    """
    Hiển thị tab Kết quả (Results) cho Race / Qualifying.
    """
    st.subheader(f"Results - {session_name}")
    res_df = session.results.copy()
    formatted_times = []
    winner_time = pd.NaT
    
    if not res_df.empty and pd.notna(res_df.iloc[0]['Time']): 
        winner_time = res_df.iloc[0]['Time']
        
    for index, row in res_df.iterrows():
        pos = row['Position']
        time_val = row['Time']
        status = str(row['Status'])
        
        if session_code in ['Q', 'SQ']:
            best_q = row.get('Q3', pd.NaT)
            if pd.isna(best_q): best_q = row.get('Q2', pd.NaT)
            if pd.isna(best_q): best_q = row.get('Q1', pd.NaT)
            
            if pd.notna(best_q):
                q_sec = best_q.total_seconds()
                formatted_times.append(f"{int(q_sec // 60):02d}:{int(q_sec % 60):02d}")
            else: 
                formatted_times.append(status)
                
        else:
            if pd.isna(time_val): 
                formatted_times.append(status)
            elif pos == 1 or pd.isna(winner_time):
                ts = time_val.total_seconds()
                formatted_times.append(f"{int(ts // 3600):02d}:{int((ts % 3600) // 60):02d}:{int(ts % 60):02d}")
            else:
                gap = time_val.total_seconds()
                formatted_times.append(f"+{int(gap // 60):02d}:{int(gap % 60):02d}")
    
    display_df = pd.DataFrame({
        'Pos': res_df['Position'].astype(str).str.replace('.0', '', regex=False),
        'Driver': res_df['FullName'], 
        'Team': res_df['TeamName'],
        'Grid': res_df['GridPosition'].astype(str).str.replace('.0', '', regex=False),
        'Status': res_df['Status'], 
        'Time': formatted_times,
        'Points': res_df['Points'].astype(str).str.replace('.0', '', regex=False)
    })
    
    st.dataframe(display_df.replace('nan', 'N/A'), width='stretch', hide_index=True)


def get_practice_results_df(session):
    """
    Hàm dùng chung để tính toán và sắp xếp kết quả phiên Practice.
    Trả về DataFrame đã được sắp xếp theo thời gian (Fastest Lap).
    """
    res_df = session.results.copy()
    lap_counts = session.laps.groupby('Driver').size().to_dict()
    
    display_data = []
    for _, row in res_df.iterrows():
        drv = row['Abbreviation']
        
        # Dùng get() và thêm cơ chế dự phòng tìm LapTime
        best_lap = row.get('BestLapTime', pd.NaT)
        if pd.isna(best_lap) and 'Abbreviation' in row:
            drv_laps = session.laps.pick_drivers(drv).dropna(subset=['LapTime'])
            if not drv_laps.empty:
                best_lap = drv_laps['LapTime'].min()
        
        # Xử lý format m:ss.3f và gán raw_seconds để sort
        fastest_str = "No Time"
        raw_seconds = float('inf') # Sử dụng vô cực để đẩy các tay đua không có thời gian xuống cuối
        
        if pd.notna(best_lap):
            ts = best_lap.total_seconds()
            raw_seconds = ts
            fastest_str = f"{int(ts // 60)}:{ts % 60:06.3f}"
            
        laps_done = lap_counts.get(drv, 0)
        
        display_data.append({
            'Driver': row['FullName'],
            'Team': row['TeamName'],
            'Fastest Lap': fastest_str,
            'Laps': laps_done,
            '_raw_time': raw_seconds  # Cột ẩn dùng để sắp xếp
        })
        
    display_df = pd.DataFrame(display_data)
    
    # Sắp xếp DataFrame theo thời gian (từ thấp đến cao)
    display_df = display_df.sort_values(by='_raw_time').reset_index(drop=True)
    
    # Tính toán lại cột Position dựa trên thứ tự sau khi sắp xếp
    positions = []
    for idx, row in display_df.iterrows():
        if row['_raw_time'] == float('inf'):
            positions.append("NC") # Not Classified nếu không có thời gian
        else:
            positions.append(str(idx + 1))
            
    # Chèn cột Pos vào vị trí đầu tiên
    display_df.insert(0, 'Pos', positions)
    
    # Xóa cột ẩn _raw_time trước khi trả về
    display_df = display_df.drop(columns=['_raw_time'])
    
    return display_df


@st.fragment
def fragment_practice_results(session, session_name):
    """
    Hiển thị tab Kết quả (Results) chuyên biệt cho Practice Sessions.
    """
    st.subheader(f"Results - {session_name}")
    display_df = get_practice_results_df(session)
    st.dataframe(display_df, width='stretch', hide_index=True)