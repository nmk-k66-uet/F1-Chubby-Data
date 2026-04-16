import streamlit as st

# Import cấu hình page ban đầu
from core.config import setup_page_config

# Thiết lập cấu hình cơ bản (Phải gọi đầu tiên)
setup_page_config()

# Khai báo các trang trong ứng dụng
page_home = st.Page("pages/home.py", title="Dashboard", icon="🏠", default=True)
page_race_analytics = st.Page("pages/race_analytics.py", title="Race Analytics", icon="📅")
page_details = st.Page("pages/details.py", title="Race Analysis", icon="🏎️")

# Chạy hệ thống điều hướng (ẩn menu bên trái theo thiết kế của bạn)
pg = st.navigation([page_home, page_race_analytics, page_details], position="hidden")
pg.run()