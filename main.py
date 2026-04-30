"""
F1 Pulse Interactive Dashboard - Main Entry Point

This is the main entry point of the Streamlit application. It initializes:
- Page configuration (layout, title, icon)
- Navigation bar at the top
- Page routing and navigation logic
"""

import os
import logging
import streamlit as st
from core.config import setup_page_config
from components.navbar import render_navbar

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    force=True,
)

# 1. Universal Setup - Configure page layout and styling
setup_page_config()

# 2. Add Navigation Bar (Top) - Display top navigation with logo, timer, and menu buttons
render_navbar()

# 3. Define Pages - Map all available pages in the application
page_home = st.Page("pages/home.py", title="Dashboard", default=True)
page_race_analytics = st.Page("pages/race_analytics.py", title="Race Analytics")
page_details = st.Page("pages/details.py", title="Race Analysis")
page_drivers = st.Page("pages/drivers.py", title="Drivers")
page_constructors = st.Page("pages/constructors.py", title="Constructors")

# 4. Routing Logic - Create navigation menu and run selected page
pg = st.navigation([page_home, page_drivers, page_constructors, page_race_analytics, page_details], position="hidden")
pg.run()