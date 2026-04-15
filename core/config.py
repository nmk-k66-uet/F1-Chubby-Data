import streamlit as st

# --- COUNTRY CODES ---
COUNTRY_CODES = {
    "Bahrain": "bh", "Saudi Arabia": "sa", "Australia": "au", "Japan": "jp", 
    "China": "cn", "USA": "us", "United States": "us", "Miami": "us", 
    "Italy": "it", "Monaco": "mc", "Spain": "es", "Canada": "ca", 
    "Austria": "at", "UK": "gb", "United Kingdom": "gb", "Hungary": "hu", 
    "Belgium": "be", "Netherlands": "nl", "Singapore": "sg", 
    "Azerbaijan": "az", "Mexico": "mx", "Brazil": "br", "Las Vegas": "us", 
    "Qatar": "qa", "Abu Dhabi": "ae", "United Arab Emirates": "ae"
}

def get_flag_url(country_name):
    code = COUNTRY_CODES.get(country_name, "un")
    return f"https://flagcdn.com/h40/{code}.png"

def setup_page_config():
    st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")

    st.markdown("""
    <style>
        [data-testid="column"] > div {
            overflow: visible !important;
        }
        div[data-baseweb="popover"] > div {
            max-height: 300px !important;
            overflow-y: auto !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        [data-testid="stSidebar"] {
            display: none !important;
        }
    </style>
    """, unsafe_allow_html=True)