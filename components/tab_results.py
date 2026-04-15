import streamlit as st
import pandas as pd

@st.fragment
def fragment_results(session, session_code, session_name):
    """
    Hiển thị tab Kết quả (Results) bao gồm:
    - Bảng thứ hạng hoàn chỉnh của phiên đua.
    - Xử lý linh hoạt format thời gian giữa Đua chính (Race) và Phân hạng (Qualifying).
    """
    st.subheader(f"Results - {session_name}")
    res_df = session.results.copy()
    formatted_times = []
    winner_time = pd.NaT
    
    # Lấy thời gian của người dẫn đầu để tính khoảng cách (Gap) cho phiên đua chính
    if not res_df.empty and pd.notna(res_df.iloc[0]['Time']): 
        winner_time = res_df.iloc[0]['Time']
        
    for index, row in res_df.iterrows():
        pos = row['Position']
        time_val = row['Time']
        status = str(row['Status'])
        
        # Xử lý format thời gian cho phiên Phân hạng (Qualifying / Sprint Shootout)
        if session_code in ['Q', 'SQ']:
            best_q = row.get('Q3', pd.NaT)
            if pd.isna(best_q): best_q = row.get('Q2', pd.NaT)
            if pd.isna(best_q): best_q = row.get('Q1', pd.NaT)
            
            if pd.notna(best_q):
                q_sec = best_q.total_seconds()
                formatted_times.append(f"{int(q_sec // 60):02d}:{int(q_sec % 60):02d}")
            else: 
                formatted_times.append(status)
                
        # Xử lý format thời gian cho phiên Đua (Race / Sprint / FP)
        else:
            if pd.isna(time_val): 
                formatted_times.append(status)
            elif pos == 1 or pd.isna(winner_time):
                # P1: Format đầy đủ H:M:S
                ts = time_val.total_seconds()
                formatted_times.append(f"{int(ts // 3600):02d}:{int((ts % 3600) // 60):02d}:{int(ts % 60):02d}")
            else:
                # P2 trở đi: Format dạng +M:S (Khoảng cách với P1)
                gap = time_val.total_seconds()
                formatted_times.append(f"+{int(gap // 60):02d}:{int(gap % 60):02d}")
    
    # Chuẩn bị DataFrame để hiển thị trên UI
    display_df = pd.DataFrame({
        'Pos': res_df['Position'].astype(str).str.replace('.0', '', regex=False),
        'Driver': res_df['FullName'], 
        'Team': res_df['TeamName'],
        'Grid': res_df['GridPosition'].astype(str).str.replace('.0', '', regex=False),
        'Status': res_df['Status'], 
        'Time': formatted_times,
        'Points': res_df['Points'].astype(str).str.replace('.0', '', regex=False)
    })
    
    # Hiển thị bảng
    st.dataframe(display_df.replace('nan', 'N/A'), width='stretch', hide_index=True)