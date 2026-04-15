import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn.metrics import classification_report, accuracy_score
import joblib
import fastf1
import warnings

warnings.filterwarnings("ignore")

# ==========================================
# CONFIGURATION & PATHS
# ==========================================
CACHE_DIR = 'f1_cache'
ASSET_DIR = os.path.join('assets', 'Models')

# Pre-Race Prediction Paths
PRE_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'historical_data.csv')
PRE_RACE_MODEL_PATH = os.path.join(ASSET_DIR, 'podium_model.pkl')
PRE_RACE_METRICS_PATH = os.path.join(CACHE_DIR, 'model_metrics.txt')

# In-Race Prediction Paths
IN_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'in_race_historical_data.csv')
IN_RACE_WIN_MODEL_PATH = os.path.join(ASSET_DIR, 'in_race_win_model.pkl')
IN_RACE_PODIUM_MODEL_PATH = os.path.join(ASSET_DIR, 'in_race_podium_model.pkl')
IN_RACE_METRICS_PATH = os.path.join(CACHE_DIR, 'in_race_metrics.txt')

# Initialize required directories
for d in [CACHE_DIR, ASSET_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_team_tier(team_name):
    """
    Categorizes F1 teams into performance tiers to help the model evaluate car performance.
    
    Args:
        team_name (str): The name of the F1 team.
    Returns:
        int: 1 (Top tier), 2 (Mid-field tier), 3 (Backmarkers).
    """
    team_str = str(team_name).lower()
    t1 = ['red bull', 'ferrari', 'mclaren', 'mercedes']
    t2 = ['aston martin', 'alpine', 'rb', 'alphatauri', 'racing point']
    if any(t in team_str for t in t1): return 1
    if any(t in team_str for t in t2): return 2
    return 3

def extract_best_q_time(row):
    """
    Extracts the fastest qualifying lap time for a given driver across all Q1, Q2, and Q3 sessions.
    
    Args:
        row (pd.Series): A row from the FastF1 Qualifying results DataFrame.
    Returns:
        float or None: The fastest lap time in seconds, or None if unavailable.
    """
    times = []
    for col in ['Q1', 'Q2', 'Q3']:
        val = row.get(col)
        if pd.notna(val):
            try: times.append(val.total_seconds())
            except: pass
    return min(times) if times else None

def extract_fp2_long_run_pace(session):
    """
    Extracts the long-run pace (race simulation pace) from Free Practice 2 or Sprint sessions.
    Only considers stints with 5 or more consecutive laps to filter out out-laps and aborted laps.
    
    Args:
        session: FastF1 session object.
    Returns:
        dict: Mapping of driver abbreviations to their pace delta compared to the fastest driver.
    """
    try:
        session.load(telemetry=False, weather=False, messages=False)
        laps = session.laps.pick_accurate()
        if laps.empty: return {}
        
        stints = laps.groupby(['Driver', 'Stint']).size().reset_index(name='LapCount')
        long_stints = stints[stints['LapCount'] >= 5]
        if long_stints.empty: return {}
        
        paces = {}
        for _, row in long_stints.iterrows():
            drv = row['Driver']
            stint_num = row['Stint']
            stint_laps = laps[(laps['Driver'] == drv) & (laps['Stint'] == stint_num)]
            median_time = stint_laps['LapTime'].median().total_seconds()
            
            if drv not in paces or median_time < paces[drv]:
                paces[drv] = median_time
                
        if not paces: return {}
        fastest_pace = min(paces.values())
        return {drv: (time - fastest_pace) for drv, time in paces.items()}
    except: return {}


# ==========================================
# MODULE 1: PRE-RACE PREDICTION CORE
# ==========================================

def initialize_model(force_retrain=False):
    """
    Loads or trains the Pre-Race Podium Prediction model.
    
    Features used:
    - GridPosition: The starting position of the driver.
    - TeamTier: The performance tier of the driver's team (1, 2, or 3).
    - QualifyingDelta: The time gap to the pole position lap (in seconds).
    - FP2_PaceDelta: The average long-run pace deficit (in seconds).
    - DriverForm: The ratio of points scored by the driver so far in the season.
    
    Args:
        force_retrain (bool): Forces the model to retrain using the latest data if True.
    Returns:
        RandomForestClassifier: The trained model for predicting pre-race podium probability.
    """
    if not force_retrain and os.path.exists(PRE_RACE_MODEL_PATH):
        return joblib.load(PRE_RACE_MODEL_PATH)
    
    if not os.path.exists(PRE_RACE_DATA_PATH):
        raise FileNotFoundError(f"[Error] Dataset not found: {PRE_RACE_DATA_PATH}")
        
    df = pd.read_csv(PRE_RACE_DATA_PATH)
    
    # Impute missing FP2 Pace Delta with the median of their Team Tier, or default to 2.0s
    df['FP2_PaceDelta'] = df['FP2_PaceDelta'].fillna(df.groupby('TeamTier')['FP2_PaceDelta'].transform('median'))
    df['FP2_PaceDelta'] = df['FP2_PaceDelta'].fillna(2.0)
        
    print("[ML] Preparing data and executing Grid Search for Pre-Race Model...")
    X = df[['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']]
    y = df['Podium']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    param_grid = {
        'n_estimators': [50, 100, 150, 200],
        'max_depth': [4, 6, 8, 10],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4]
    }
    
    base_model = RandomForestClassifier(random_state=42, class_weight='balanced')
    grid_search = GridSearchCV(estimator=base_model, param_grid=param_grid, cv=5, scoring='f1', n_jobs=-1, verbose=1)
    
    grid_search.fit(X_train, y_train)
    best_model = grid_search.best_estimator_
    
    y_pred = best_model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)
    
    with open(PRE_RACE_METRICS_PATH, 'w', encoding='utf-8') as f:
        f.write("=== F1 PRE-RACE PODIUM PREDICTION - PERFORMANCE REPORT ===\n")
        f.write(f"Training Timestamp: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Best Hyperparameters: {grid_search.best_params_}\n")
        f.write(f"Overall Accuracy: {acc:.4f}\n")
        f.write("-" * 60 + "\n")
        f.write("Classification Report:\n")
        f.write(report)
    
    joblib.dump(best_model, PRE_RACE_MODEL_PATH)
    print(f"[ML] Pre-Race Model trained and saved successfully.")
    
    return best_model

def predict_podium_probabilities(model, current_grid_df):
    """
    Predicts the podium probabilities for a given race grid.
    Normalizes the probabilities so the total expected outcome equals 3.0 (3 podium spots).
    """
    features = current_grid_df[['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']]
    probabilities = model.predict_proba(features)[:, 1]
    
    factor = 3.0 / np.sum(probabilities) if np.sum(probabilities) > 0 else 1
    current_grid_df['Podium_Probability'] = np.clip(probabilities * factor, 0, 0.99)
    
    return current_grid_df.sort_values(by='Podium_Probability', ascending=False)

def prepare_race_features(year, round_num):
    """
    Extracts live FastF1 features for the current race weekend to perform predictions.
    """
    print(f"\n[INFERENCE] Extracting Pre-Race features for Season {year} - Round {round_num}...")
    
    # 1. Qualy Data
    pole_time_sec = None
    q_res = pd.DataFrame()
    try:
        q_session = fastf1.get_session(year, round_num, 'Q')
        q_session.load(telemetry=False, weather=False, messages=False)
        q_res = q_session.results
        all_q_times = []
        for _, r in q_res.iterrows():
            for c in ['Q1', 'Q2', 'Q3']:
                if pd.notna(r.get(c)): all_q_times.append(r[c].total_seconds())
        if all_q_times: pole_time_sec = min(all_q_times)
    except: pass
    
    # 2. Long Run Data (FP2 or Sprint Race)
    fp2_deltas = {}
    try:
        schedule = fastf1.get_event_schedule(year)
        event_row = schedule[schedule['RoundNumber'] == round_num].iloc[0]
        format_type = event_row.get('EventFormat', 'conventional').lower()
        
        pace_session_code = 'S' if format_type in ['sprint', 'sprint_qualifying'] else 'FP2'
        pace_session = fastf1.get_session(year, round_num, pace_session_code)
        fp2_deltas = extract_fp2_long_run_pace(pace_session)
    except: pass
    
    # 3. Grid Data
    grid_session = fastf1.get_session(year, round_num, 'R')
    try:
        grid_session.load(telemetry=False, weather=False, messages=False)
        base_results = grid_session.results
    except:
        base_results = q_res

    if base_results.empty:
        raise ValueError("Failed to retrieve Grid starting positions for this session.")

    # 4. Driver Form
    current_standings = {}
    try:
        for rnd in range(1, round_num):
            past_race = fastf1.get_session(year, rnd, 'R')
            past_race.load(telemetry=False, weather=False, messages=False)
            for _, r in past_race.results.iterrows():
                drv = r['Abbreviation']
                current_standings[drv] = current_standings.get(drv, 0) + pd.to_numeric(r['Points'], errors='coerce')
    except: pass
    max_pts = max(1, (round_num - 1) * 26)
    
    tier_fp2_avg = {1: [], 2: [], 3: []}
    for drv, delta in fp2_deltas.items():
        drv_row = base_results[base_results['Abbreviation'] == drv]
        team = drv_row['TeamName'].iloc[0] if not drv_row.empty else ""
        tier = get_team_tier(team)
        tier_fp2_avg[tier].append(delta)
    tier_fp2_avg = {k: (np.median(v) if v else 1.5) for k, v in tier_fp2_avg.items()}
    
    grid_data = []
    for _, row in base_results.iterrows():
        drv = row['Abbreviation']
        grid_pos = pd.to_numeric(row.get('GridPosition', row.get('Position')), errors='coerce')
        if pd.isna(grid_pos) or grid_pos == 0: grid_pos = 20
            
        team_name = row['TeamName']
        tier = get_team_tier(team_name)
        
        q_delta = 2.0
        if pole_time_sec is not None and not q_res.empty and drv in q_res['Abbreviation'].values:
            drv_q = q_res[q_res['Abbreviation'] == drv].iloc[0]
            drv_times = [drv_q.get(c).total_seconds() for c in ['Q1', 'Q2', 'Q3'] if pd.notna(drv_q.get(c))]
            if drv_times:
                q_delta = min(drv_times) - pole_time_sec
                
        fp2_delta = fp2_deltas.get(drv, tier_fp2_avg[tier])
        form = current_standings.get(drv, 0) / max_pts
        color = f"#{row['TeamColor']}" if 'TeamColor' in row and str(row['TeamColor']) != 'nan' else '#FFFFFF'
        
        grid_data.append({
            'Driver': drv, 'FullName': row.get('FullName', drv), 'Team': team_name,
            'GridPosition': int(grid_pos), 'TeamTier': tier,
            'QualifyingDelta': max(0, q_delta), 'FP2_PaceDelta': fp2_delta,
            'DriverForm': form, 'Color': color
        })
    
    return pd.DataFrame(grid_data)


# ==========================================
# MODULE 2: IN-RACE PREDICTION CORE
# ==========================================

def train_in_race_model(force_retrain=False):
    """
    Trains parallel models for live In-Race (Lap-by-Lap) predictions.
    
    Features used:
    - LapFraction: Race progression status (Current Lap / Total Laps). Range: 0.0 -> 1.0
    - CurrentPosition: The rank of the driver at the given lap.
    - GapToLeader: Time gap to the race leader (in seconds).
    - TyreLife: Number of laps completed on the current tyre set.
    - CompoundIdx: Encoded tyre compound.
    - IsPitOut: Flag indicating if the driver just exited the pit lane.
    
    Args:
        force_retrain (bool): Forces the models to retrain using the latest data if True.
    Returns:
        tuple: (best_win_model, best_podium_model)
    """
    if not force_retrain and os.path.exists(IN_RACE_WIN_MODEL_PATH) and os.path.exists(IN_RACE_PODIUM_MODEL_PATH):
        print("[ML] Found cached In-Race Models. Loading...")
        return joblib.load(IN_RACE_WIN_MODEL_PATH), joblib.load(IN_RACE_PODIUM_MODEL_PATH)
        
    print("[ML] Initializing In-Race Models (Win & Podium) training process...")
    
    if not os.path.exists(IN_RACE_DATA_PATH):
        raise FileNotFoundError(f"[Error] Dataset not found: {IN_RACE_DATA_PATH}. Run InRace_DataCrawler first.")
        
    df = pd.read_csv(IN_RACE_DATA_PATH)
    df = df.dropna(subset=['CurrentPosition', 'GapToLeader', 'TyreLife'])
    
    print(f"[ML] In-Race Training Dataset size: {len(df)} laps.")
    
    X = df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
    
    # Create two separate target variables
    y_win = (df['FinalPosition'] == 1).astype(int)
    y_podium = (df['FinalPosition'] <= 3).astype(int)
    
    X_train, X_test, y_train_w, y_test_w, y_train_p, y_test_p = train_test_split(
        X, y_win, y_podium, test_size=0.2, random_state=42, stratify=y_podium
    )
    
    param_dist = {
        'n_estimators': [100, 150],
        'max_depth': [8, 12, 15],
        'min_samples_split': [5, 10]
    }
    
    print("[ML] Tuning In-Race WIN Predictor Model...")
    base_win = RandomForestClassifier(random_state=42, class_weight='balanced')
    search_win = RandomizedSearchCV(estimator=base_win, param_distributions=param_dist, 
                                n_iter=5, cv=3, scoring='f1', n_jobs=-1, verbose=1, random_state=42)
    search_win.fit(X_train, y_train_w)
    best_win = search_win.best_estimator_
    
    print("[ML] Tuning In-Race PODIUM Predictor Model...")
    base_pod = RandomForestClassifier(random_state=42, class_weight='balanced')
    search_pod = RandomizedSearchCV(estimator=base_pod, param_distributions=param_dist, 
                                n_iter=5, cv=3, scoring='f1', n_jobs=-1, verbose=1, random_state=42)
    search_pod.fit(X_train, y_train_p)
    best_pod = search_pod.best_estimator_
    
    # Evaluate Models
    acc_w = accuracy_score(y_test_w, best_win.predict(X_test))
    rep_w = classification_report(y_test_w, best_win.predict(X_test))
    
    acc_p = accuracy_score(y_test_p, best_pod.predict(X_test))
    rep_p = classification_report(y_test_p, best_pod.predict(X_test))
    
    with open(IN_RACE_METRICS_PATH, 'w', encoding='utf-8') as f:
        f.write("=== IN-RACE MODEL METRICS ===\n\n")
        f.write("--- WIN MODEL ---\n")
        f.write(f"Best Parameters: {search_win.best_params_}\n")
        f.write(f"Accuracy: {acc_w:.4f}\n")
        f.write(rep_w + "\n\n")
        
        f.write("--- PODIUM MODEL ---\n")
        f.write(f"Best Parameters: {search_pod.best_params_}\n")
        f.write(f"Accuracy: {acc_p:.4f}\n")
        f.write(rep_p + "\n")
        
    joblib.dump(best_win, IN_RACE_WIN_MODEL_PATH)
    joblib.dump(best_pod, IN_RACE_PODIUM_MODEL_PATH)
    
    print("[ML] Both In-Race models trained and cached successfully!")
    return best_win, best_pod

def predict_live_lap(models, live_lap_df):
    """
    Predicts live Win and Podium probabilities for a given lap during a race.
    
    Args:
        models (tuple): The trained (win_model, podium_model).
        live_lap_df (pd.DataFrame): Current status of 20 drivers at Lap N.
    Returns:
        pd.DataFrame: The input dataframe with added probability columns, sorted by Win Probability.
    """
    win_model, podium_model = models
    features = live_lap_df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
    
    prob_win = win_model.predict_proba(features)[:, 1]
    prob_pod = podium_model.predict_proba(features)[:, 1]
    
    # Normalize probabilities: Total Win expected = 1.0, Total Podium expected = 3.0
    factor_w = 1.0 / np.sum(prob_win) if np.sum(prob_win) > 0 else 1
    factor_p = 3.0 / np.sum(prob_pod) if np.sum(prob_pod) > 0 else 1
    
    live_lap_df['Live_Win_Prob'] = np.clip(prob_win * factor_w, 0, 0.99)
    live_lap_df['Live_Podium_Prob'] = np.clip(prob_pod * factor_p, 0, 0.99)
    
    # Logical Constraint: A driver's chance of winning cannot exceed their chance of getting a podium
    live_lap_df['Live_Win_Prob'] = np.minimum(live_lap_df['Live_Win_Prob'], live_lap_df['Live_Podium_Prob'])
    
    return live_lap_df.sort_values(by=['Live_Win_Prob', 'Live_Podium_Prob'], ascending=[False, False])

# ==========================================
# TEST EXECUTION
# ==========================================
if __name__ == '__main__':
    print("Initializing Standalone Retrain...")
    # Uncomment the following lines to test retrain manually
    initialize_model(force_retrain=True)
    train_in_race_model(force_retrain=True)
    print("Done.")