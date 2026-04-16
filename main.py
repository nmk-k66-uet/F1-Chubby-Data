import streamlit as st

# Import cấu hình page và navbar
from core.config import setup_page_config
from components.navbar import render_navbar

# 1. Thiết lập cấu hình cơ bản (Phải gọi đầu tiên)
setup_page_config()

# 2. HIỂN THỊ THANH ĐIỀU HƯỚNG TRÊN CÙNG MỌI TRANG
# Điều này đảm bảo dù bạn ở Dashboard hay Race Analytics, Navbar vẫn cố định ở trên
render_navbar()

# 3. Khai báo danh sách các trang trong ứng dụng
page_home = st.Page("pages/home.py", title="Dashboard", default=True)
page_race_analytics = st.Page("pages/race_analytics.py", title="Race Analytics")
page_details = st.Page("pages/details.py", title="Race Analysis")
page_drivers = st.Page("pages/drivers.py", title="Drivers")
page_constructors = st.Page("pages/constructors.py", title="Constructors")

# 4. Chạy hệ thống điều hướng (ẩn menu mặc định bên trái)
pg = st.navigation([page_home, page_drivers, page_constructors, page_race_analytics, page_details], position="hidden")
pg.run()