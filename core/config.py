"""
Configuration Module - Global Settings and Styling

This module contains:
- Country code mappings for flag URL generation
- Page configuration and global CSS styling
"""

import streamlit as st

# --- COUNTRY CODES ---
# Maps country names to their ISO 2-letter country codes for flag CDN
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
    """
    Generates a URL to the flag image for a given country.
    
    Args:
        country_name (str): The name of the country (e.g., "Bahrain", "Monaco").
    
    Returns:
        str: URL to the flag image from flagcdn.com (40px height).
             Returns UN flag if country not found.
    """
    code = COUNTRY_CODES.get(country_name, "un")
    return f"https://flagcdn.com/h40/{code}.png"

def setup_page_config():
    """
    Initializes Streamlit page configuration and applies global CSS styling.
    
    This function:
    - Sets page title and layout to wide mode
    - Hides the sidebar
    - Styles columns and popovers
    - Removes default Streamlit controls
    
    Output: Modifies global Streamlit configuration and injects CSS styling.
    """
    st.set_page_config(page_title="F1 Pulse Interactive Dashboard", layout="wide", page_icon="🏎️")

    st.markdown("""
    <style>
        /* Allow columns to have visible overflow for tooltips and overlays */
        [data-testid="column"] > div {
            overflow: visible !important;
        }
        
        /* Constrain popover height and add scrolling for long lists */
        div[data-baseweb="popover"] > div {
            max-height: 300px !important;
            overflow-y: auto !important;
        }
        
        /* Hide Streamlit's collapsed control button */
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        
        /* Hide the entire sidebar */
        [data-testid="stSidebar"] {
            display: none !important;
        }
    </style>
    """, unsafe_allow_html=True)