"""
Pre-Race Predictor UI Component - Podium Probability Analysis

This component provides:
- AI-powered podium probability predictions using Random Forest model
- Setup Profiler visualization (Downforce vs. Drag analysis)
- AI-generated tactical analysis using Google Gemini
- Model retraining capability with fresh data
"""

import streamlit as st
import os
import pandas as pd
import plotly.express as px
from google import genai
from core import ml_core

@st.fragment
def render_predictor_tab(session, year, round_num, event_name):
    """
    Renders the Pre-Race Podium Probability Predictor tab.
    
    Features:
    1. Podium Probability Predictions: Displays ML model predictions for each driver
    2. Setup Profiler: Scatter chart showing Top Speed vs Average Speed quadrant analysis
    3. Tactical Analysis: AI-generated insights from Google Gemini
    
    Args:
        session: FastF1 session object containing lap/telemetry data
        year (int): F1 season year
        round_num (int): Race round number
        event_name (str): Name of the race event (e.g., "Bahrain Grand Prix")
    
    Output: Displays prediction results, charts, and AI analysis in UI
    """
    st.subheader("Pre-Race Podium Probability Predictor")
    
    current_race_id = f"{year}_{round_num}"
    
    # === Clear Cache When Switching Races ===
    # If user navigates to a different race, clear previous predictions
    if st.session_state.get('predictions_race_id') != current_race_id:
        st.session_state.pop('predictions_df', None)
        st.session_state.pop('setup_profiler_fig', None)
        st.session_state.pop('gemini_insight', None)
    
    # === Load Gemini API Key ===
    gemini_key = ""
    key_file_path = "assets/gemini_key.txt"
    if os.path.exists(key_file_path):
        with open(key_file_path, "r", encoding="utf-8") as f:
            gemini_key = f.read().strip()
    
    gemini_client = None
    if gemini_key:
        gemini_client = genai.Client(api_key=gemini_key)
    
    # === CONTROL BUTTONS ===
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        # Button to run predictions and generate analysis
        run_ai = st.button("Generate Predictions & Analysis", type="primary", width='stretch')
    with col_btn2:
        # Button to retrain model with fresh data
        retrain_ai = st.button("Retrain Model (If fresh data exists)", width='stretch')
        
    if retrain_ai:
        with st.spinner("Retraining the model from historical data..."):
            ml_core.initialize_model(force_retrain=True)
            st.success("Model retrained successfully!")
            
    # === PREDICTION EXECUTION LOGIC ===
    if run_ai:
        with st.spinner("Running simulations and generating technical insights..."):
            try:
                # 1. LOAD AND RUN ML MODEL
                model = ml_core.initialize_model(force_retrain=False) 
                inference_df = ml_core.prepare_race_features(year, round_num) 
                preds_df = ml_core.predict_podium_probabilities(model, inference_df) 
                
                st.session_state['predictions_df'] = preds_df
                st.session_state['predictions_race_id'] = current_race_id
                
                # 2. BUILD SETUP PROFILER CHART (Top Speed vs Average Speed)
                # Analyzes downforce vs drag trade-off for top 10 drivers
                setup_data = []
                for _, row in preds_df.head(10).iterrows():
                    drv = row['Driver']
                    try:
                        # Get fastest lap for this driver and extract telemetry
                        drv_lap = session.laps.pick_drivers(drv).pick_fastest()
                        if not pd.isna(drv_lap['LapTime']):
                            tel = drv_lap.get_telemetry()
                            if not tel.empty and 'Speed' in tel.columns:
                                setup_data.append({
                                    'Driver': drv,
                                    'FullName': row['FullName'],
                                    'Top Speed (km/h)': tel['Speed'].max(),      # Maximum speed (low drag indicator)
                                    'Average Speed (km/h)': tel['Speed'].mean(),  # Average speed (downforce indicator)
                                    'Color': row['Color']                          # Team color
                                })
                    except: 
                        pass
                        
                if setup_data:
                    setup_df = pd.DataFrame(setup_data)
                    avg_x = setup_df['Average Speed (km/h)'].mean()
                    avg_y = setup_df['Top Speed (km/h)'].mean()

                    # Create scatter plot
                    fig_setup = px.scatter(
                        setup_df, x='Average Speed (km/h)', y='Top Speed (km/h)',
                        text='Driver', color='Driver',
                        color_discrete_map={r['Driver']: r['Color'] for _, r in setup_df.iterrows()}
                    )
                    fig_setup.update_traces(textposition='top center', marker=dict(size=14, line=dict(width=1, color='White')))
                    
                    # Add crosshair lines (horizontal and vertical) showing average values
                    fig_setup.add_vline(x=avg_x, line_dash="dash", line_color="rgba(255,255,255,0.3)")
                    fig_setup.add_hline(y=avg_y, line_dash="dash", line_color="rgba(255,255,255,0.3)")

                    # Add quadrant labels explaining setup types
                    # Quadrant 1: High Downforce + Low Drag (Efficient)
                    fig_setup.add_annotation(xref="paper", yref="paper", x=0.95, y=0.95, 
                        text="<b>Efficient</b><br>(High DF / Low Drag)", showarrow=False, 
                        font=dict(color="#00cc66", size=11), align="right")
                    
                    # Quadrant 2: High Drag Focus
                    fig_setup.add_annotation(xref="paper", yref="paper", x=0.95, y=0.05, 
                        text="<b>High Drag</b><br>(Downforce Focused)", showarrow=False, 
                        font=dict(color="#ff4b4b", size=11), align="right")
                    
                    # Quadrant 3: Low Drag Focus (Speed Focused)
                    fig_setup.add_annotation(xref="paper", yref="paper", x=0.05, y=0.95, 
                        text="<b>Low Drag</b><br>(Speed Focused)", showarrow=False, 
                        font=dict(color="#00ccff", size=11), align="left")
                    
                    # Quadrant 4: Inefficient Setup
                    fig_setup.add_annotation(xref="paper", yref="paper", x=0.05, y=0.05, 
                        text="<b>Inefficient</b><br>(Low DF / High Drag)", showarrow=False, 
                        font=dict(color="#888", size=11), align="left")

                    # Update layout with styling
                    fig_setup.update_layout(
                        title=dict(text="Setup Profiler (Downforce vs Drag)", font=dict(size=16)),
                        xaxis_title="Average Speed (Higher = Better Downforce)",
                        yaxis_title="Top Speed (Higher = Lower Drag)",
                        showlegend=False, height=500,
                        plot_bgcolor='rgba(20,20,20,0.5)', paper_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0, r=0, t=50, b=0),
                        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)")
                    )
                    st.session_state['setup_profiler_fig'] = fig_setup
                
                # 3. GENERATE AI TACTICAL ANALYSIS USING GOOGLE GEMINI
                if gemini_client:
                    # Prepare race data summary for Gemini
                    prompt_data = preds_df.head(10)[['Driver', 'FullName', 'GridPosition', 'Podium_Probability', 'QualifyingDelta', 'FP2_PaceDelta']].to_string(index=False)
                    
                    # Detailed prompt for technical analysis
                    prompt = f"""
                    You are a world-class F1 Chief Race Engineer.
                    Analyze the following race simulation data for the {event_name} {year}. 
                    Do NOT mention AI or Machine Learning. Treat these values as internal engineering simulations.

                    SIMULATION DATA:
                    {prompt_data}

                    Requirements:
                    - Provide a highly technical tactical briefing (200-250 words) in English.
                    - Use clear bold headings and bullet points for readability.
                    - Focus on:
                        * Primary Contenders: Analyze favorites based on Qualifying Delta and simulation probabilities.
                        * Tactical 'Dark Horse': Identify a driver outside the Top 4 with strong long-run pace (FP2_PaceDelta) likely to challenge the podium.
                        * Strategic Implications: Impact of track position vs. race pace on pit window decisions.
                    - Tone: Strictly data-driven, precise, and professional.
                    """
                    
                    response = gemini_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt
                    )
                    st.session_state['gemini_insight'] = response.text
                else:
                    st.session_state['gemini_insight'] = "⚠️ Gemini API Key not found in assets/gemini_key.txt."

            except Exception as e:
                st.error(f"Analysis error: {str(e)}")

    # === DISPLAY CACHED RESULTS ===
    if 'predictions_df' in st.session_state:
        predictions_df = st.session_state['predictions_df']
        st.divider()
        st.markdown("### Podium Probability Predictions")
        
        col_chart, col_setup = st.columns([1.2, 1])
        
        with col_chart:
            top_10_df = predictions_df.head(10).sort_values('Podium_Probability', ascending=True)
            fig_pred = px.bar(
                top_10_df, 
                x='Podium_Probability', 
                y='Driver',
                orientation='h',
                color='Driver',
                color_discrete_map={row['Driver']: row['Color'] for _, row in predictions_df.iterrows()},
                text=top_10_df['Podium_Probability'].apply(lambda x: f"{x:.1%}")
            )
            fig_pred.update_layout(
                title=dict(text="Top 10 Probability Standings", font=dict(size=16)),
                xaxis_title="Probability to Finish in Top 3",
                yaxis_title="",
                yaxis=dict(categoryorder='total ascending'),
                xaxis=dict(tickformat=".0%", range=[0, 1]),
                showlegend=False, height=500,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0, r=0, t=50, b=0)
            )
            fig_pred.update_traces(textposition='outside', cliponaxis=False)
            st.plotly_chart(fig_pred, width='stretch')
        
        with col_setup:
            if 'setup_profiler_fig' in st.session_state:
                st.plotly_chart(st.session_state['setup_profiler_fig'], width='stretch')
            else:
                st.info("Insufficient Telemetry data for Setup Profiler.")

        # Tactical Analysis from Gemini
        st.divider()
        st.markdown("### Tactical Analysis")
        if 'gemini_insight' in st.session_state:
            # Direct Markdown to preserve bullet points
            st.markdown(st.session_state['gemini_insight'])