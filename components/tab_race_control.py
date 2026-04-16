import streamlit as st
import pandas as pd

@st.fragment
def fragment_race_control(session):
    """
    Hiển thị tab Race Control dưới dạng danh sách các thẻ sự kiện (Event Cards),
    cho phép lọc theo Category hoặc loại Cờ (Flag).
    """
    try:
        rcm_df = session.race_control_messages.copy()
    except Exception:
        st.info("No data from Race Control for this session.")
        return

    if rcm_df.empty:
        st.info("No Race Control messages for this session.")
        return

    # Đảm bảo cột Flag tồn tại để tránh lỗi nếu phiên đua không có cờ nào
    if 'Flag' not in rcm_df.columns:
        rcm_df['Flag'] = ''

    # --- CHUẨN HÓA DỮ LIỆU ĐỂ LỌC CHÍNH XÁC ---
    rcm_df['Category'] = rcm_df['Category'].astype(str).str.strip()
    
    def normalize_flag(f):
        f_str = str(f).strip()
        if f_str.lower() in ['none', 'nan', '']:
            return ''
        return f_str.title().replace(' And ', ' and ')
        
    rcm_df['Flag'] = rcm_df['Flag'].apply(normalize_flag)

    # --- TIÊU ĐỀ VÀ THỐNG KÊ ---
    st.subheader("Race Control Timeline")
    
    # Tạo một vùng trống (placeholder) để điền số lượng sự kiện sau khi lọc xong
    # Vị trí của nó sẽ nằm trên 2 combobox
    count_placeholder = st.empty()

    # --- BỘ LỌC (FILTERS) ---
    categories = ['Flag', 'Other', 'SafetyCar', 'SessionStatus']
    flags = ['Black and White', 'Blue', 'Chequered', 'Clear', 'Double Yellow', 'Green', 'Yellow', 'Red']

    col1, col2 = st.columns(2)
    with col1:
        sel_categories = st.multiselect("Filter by Category", categories, default=[])
    with col2:
        sel_flags = st.multiselect("Filter by Flag", flags, default=[])

    # Áp dụng logic lọc dữ liệu (Dùng phép toán OR)
    if sel_categories and sel_flags:
        filtered_df = rcm_df[rcm_df['Category'].isin(sel_categories) | rcm_df['Flag'].isin(sel_flags)]
    elif sel_categories:
        filtered_df = rcm_df[rcm_df['Category'].isin(sel_categories)]
    elif sel_flags:
        filtered_df = rcm_df[rcm_df['Flag'].isin(sel_flags)]
    else:
        filtered_df = rcm_df

    # Cập nhật số lượng sự kiện hiển thị lên placeholder đã đặt ở trên
    count_placeholder.caption(f"**{len(filtered_df)}** / **{len(rcm_df)}** events recorded")

    st.divider()

    # --- HIỂN THỊ DANH SÁCH EVENT CÓ SCROLL ---
    if filtered_df.empty:
        st.warning("Không tìm thấy sự kiện nào khớp với bộ lọc.")
        return

    cat_icons = {
        'Flag': '🚩', 'Other': 'ℹ️', 'SafetyCar': '🚓', 'SessionStatus': '🚥'
    }
    
    flag_colors = {
        'Red': ('#ff4b4b', '#ffffff'),
        'Yellow': ('#ffd700', '#000000'),
        'Double Yellow': ('#ffaa00', '#000000'),
        'Green': ('#00cc66', '#ffffff'),
        'Clear': ('#00cc66', '#ffffff'),
        'Blue': ('#00aaff', '#ffffff'),
        'Black and White': ('#e0e0e0', '#000000'),
        'Chequered': ('#ffffff', '#000000')
    }

    # Gom toàn bộ HTML vào một chuỗi kết hợp với thẻ Div Scrollable
    # QUAN TRỌNG: Không thụt lề chuỗi này để tránh bị nhận diện thành Markdown Code Block
    cards_html = """
<style>
    .rc-scroll-container {
        max-height: 550px;
        overflow-y: auto;
        padding-right: 12px;
    }
    /* Tuỳ chỉnh thiết kế thanh cuộn (Scrollbar) cho giao diện tối */
    .rc-scroll-container::-webkit-scrollbar {
        width: 6px;
    }
    .rc-scroll-container::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 4px;
    }
    .rc-scroll-container::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 4px;
    }
    .rc-scroll-container::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.3);
    }
</style>
<div class="rc-scroll-container">
"""

    for _, row in filtered_df.iterrows():
        # Xử lý format thời gian
        t = row.get('Time')
        if pd.notna(t):
            if hasattr(t, 'total_seconds'):
                ts = t.total_seconds()
                h, m, s = int(ts // 3600), int((ts % 3600) // 60), int(ts % 60)
                time_str = f"T+{h:02d}:{m:02d}:{s:02d}"
            else:
                time_str = t.strftime("%H:%M:%S")
        else:
            time_str = "00:00:00"

        cat = row.get('Category', '')
        flag = row.get('Flag', '')
        msg = str(row.get('Message', ''))

        cat_icon = cat_icons.get(cat, '📌')
        badges_html = f"<span style='background-color: rgba(255,255,255,0.1); padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; margin-right: 8px;'>{cat_icon} {cat}</span>"
        
        border_color = "#555555"
        
        if flag:
            bg_color, text_color = flag_colors.get(flag, ('#555555', '#ffffff'))
            border_color = bg_color
            badges_html += f"<span style='background-color: {bg_color}; color: {text_color}; padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold;'>{flag}</span>"
        elif cat == 'SafetyCar':
            border_color = "#ffaa00"

        # Cấu trúc từng thẻ (Ép sát lề trái để Markdown render thành HTML chuẩn)
        cards_html += f'''
<div style="background-color: #1e2025; border-left: 4px solid {border_color}; padding: 12px 16px; margin-bottom: 12px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
    <div style="margin-bottom: 6px; display: flex; align-items: center;">
        <span style="font-family: monospace; color: #a0a0a0; font-size: 0.9rem; margin-right: 12px;">⏱️ {time_str}</span>
        {badges_html}
    </div>
    <div style="font-size: 1.05rem; color: #ffffff; line-height: 1.4;">{msg}</div>
</div>
'''
        
    cards_html += "</div>" # Đóng thẻ container

    # Render toàn bộ HTML một lần duy nhất
    st.markdown(cards_html, unsafe_allow_html=True)