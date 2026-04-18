# 🏎️ F1 Data Analytics & Live Race Predictor

A comprehensive Formula 1 data analytics and real-time prediction system. Built on **Streamlit**, this application provides intuitive visualizations of race strategies and telemetry, while integrating advanced Machine Learning models to predict win and podium probabilities on a lap-by-lap basis.

## 🌟 Key Features

* **Real-time Simulation & Leaderboard:** Simulates a live race data stream with a continuously updating Timing Tower and Interval/Gap tracking.

* **Dynamic ML Predictor:** Utilizes *Random Forest Classifier* models to infer Win and Podium probabilities lap-by-lap, visualized through Sparklines and Radar Charts.

* **Track Dominance & Telemetry:** Analyzes speed, throttle, and RPM across mini-sectors of the track.

* **Comprehensive Analytics:** Compares lap times, tire strategies, and season standings.

## 📂 Directory Structure

The project follows a **Modular Multi-page App** architecture, separating the Frontend (UI/UX) and Backend (Data/ML).

```text
F1-Chubby-Data/
│
├── main.py                     # Streamlit application entry point
├── requirements.txt            # Python dependencies (streamlit, fastf1, scikit-learn, plotly...)
│
├── 📁 pages/                   # Independent UI pages (Streamlit Multi-page)
│   ├── home.py                 # Homepage: Season overview, Standings, Next race countdown
│   ├── race_analytics.py       # Race Calendar selection + Video Intro Overlay
│   ├── details.py              # Central hub containing all analytics tabs for a selected race
│   ├── drivers.py              # Detailed driver standings
│   └── constructors.py         # Detailed constructor standings
│
├── 📁 components/              # Reusable UI Modules (Tabs) for details.py
│   ├── navbar.py               # Global navigation bar
│   ├── tab_live_race.py        # Live Race simulation tab (Timing Tower, Head-to-Head, ML Inspector)
│   ├── tab_telemetry.py        # Telemetry charts (Speed, RPM, Gear) across track segments
│   ├── tab_track_dominance.py  # Track map highlighting the fastest driver in each mini-sector
│   ├── tab_lap_times.py        # Lap time scatter plot comparison
│   ├── tab_strategy.py         # Tire usage history and pit-stop times
│   ├── tab_positions.py        # Position changes chart throughout the race
│   ├── tab_results.py          # Final race classification board
│   ├── tab_race_control.py     # Race Control message history (Yellow flags, SC, VSC)
│   └── predictor_ui.py         # UI for the Pre-Race prediction feature
│
├── 📁 core/                    # Backend Logic & Data Pipelines
│   ├── data_loader.py          # FastF1 interaction, data cleaning, and packaging
│   ├── ml_core.py              # ML Pipeline: Training, Feature Engineering, and Live Inference
│   ├── config.py               # Constants, team colors, and national flag URLs
│   └── data_crawler.py         # Script for large-scale historical data collection
│
├── 📁 assets/                  # Static Files
│   ├── 📁 BGS/                 # Circuit background images
│   ├── 📁 Cars/ & 📁 Teams/    # Team car images and logos
│   ├── 📁 Drivers/             # Driver portraits
│   └── 📁 Models/              # Pre-trained machine learning models (.pkl)
│       ├── in_race_win_model.pkl    
│       ├── in_race_podium_model.pkl 
│       └── podium_model.pkl         
│
└── 📁 f1_cache/                # FastF1 temporary cache directory to optimize API calls
```

## 🔄 Data & Machine Learning Pipeline

The system is designed to handle complex F1 data smoothly on a web platform, comprising two core pipelines:

### 1. Historical Analytics Pipeline

1. **User Request:** The user selects a specific year and race event in `race_analytics.py`.

2. **Overlay Preloading:** While data loads, an F1 Intro video iframe overlays the screen to enhance UX.

3. **Data Fetching (`core/data_loader.py`):** The app calls the `fastf1` library to download event data.

4. **Caching:** Heavy data (millions of telemetry points) is cached in `f1_cache/`. Subsequent loads take < 1 second.

5. **UI Rendering (`components/`):** Data is routed to various tabs. Pandas is used for data wrangling before rendering interactive charts via Plotly or Altair.

### 2. Machine Learning Inference Pipeline

The system employs **Random Forest Classifiers** (`sklearn`) divided into two separate tasks:

**A. Pre-Race Prediction**

* **Features:** Grid Position, FP2 Long Run Pace Delta, Driver Form, Team Performance Tier.

* **Process:** Initial data is extracted after Saturday's Qualifying. The system calculates probability distributions and displays them in the *Race Predictor* tab.

**B. Live-Race Lap-by-Lap Inference**

* The `tab_live_race.py` module slices historical data into a simulated stream (updating every 3 seconds).

* **Instant Features:** `LapFraction` (Race progress), `CurrentPosition`, `GapToLeader`, `TyreLife`, and `CompoundIdx`.

* **Inference Engine (`core/ml_core.py`):** The `predict_live_lap()` function feeds these features into `in_race_win_model.pkl` and `in_race_podium_model.pkl`.

* **Visualizing UI:** Returns to the *ML Inspector Panel*. The UI calculates momentum, updates Altair Sparklines, and redraws Plotly Radar charts to explain *why* a driver has a high win probability.

## 🚀 Installation & Setup

Ensure you have Python 3.9+ installed.

**1. Clone the repository**

```bash
git clone https://github.com/your-username/f1-chubby-data.git
cd f1-chubby-data
```

**2. Install Dependencies**

```bash
pip install -r requirements.txt
```

*(Key libraries: `streamlit`, `pandas`, `fastf1`, `scikit-learn`, `plotly`, `altair`)*

**3. Train Models (Optional - If you want to generate new models)**

```bash
python core/ml_core.py
```

*Note: This process requires the `historical_data.csv` dataset in the `f1_cache` directory.*

**4. Run the Application**

```bash
streamlit run main.py
```

*Developed with Data & Speed 🏁*
