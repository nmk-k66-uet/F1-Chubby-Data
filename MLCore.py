import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import classification_report, accuracy_score
import joblib
import fastf1
import warnings

warnings.filterwarnings("ignore")

CACHE_DIR = 'f1_cache'
MODEL_PATH = os.path.join(CACHE_DIR, 'podium_model.pkl')
DATA_PATH = os.path.join(CACHE_DIR, 'historical_data.csv')
METRICS_PATH = os.path.join(CACHE_DIR, 'model_metrics.txt')

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_team_tier(team_name):
    team_str = str(team_name).lower()
    t1 = ['red bull', 'ferrari', 'mclaren', 'mercedes']
    t2 = ['aston martin', 'alpine', 'rb', 'alphatauri', 'racing point']
    if any(t in team_str for t in t1): return 1
    if any(t in team_str for t in t2): return 2
    return 3

def extract_best_q_time(row):
    times = []
    for col in ['Q1', 'Q2', 'Q3']:
        val = row.get(col)
        if pd.notna(val):
            try: times.append(val.total_seconds())
            except: pass
    return min(times) if times else None

def extract_fp2_long_run_pace(session):
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
# Model Training
# ==========================================

def initialize_model(force_retrain=False):
    if not force_retrain and os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Không tìm thấy file {DATA_PATH}")
        
    df = pd.read_csv(DATA_PATH)
    
    df['FP2_PaceDelta'] = df['FP2_PaceDelta'].fillna(df.groupby('TeamTier')['FP2_PaceDelta'].transform('median'))
    df['FP2_PaceDelta'] = df['FP2_PaceDelta'].fillna(2.0)
        
    print("[ML] Đang chuẩn bị dữ liệu và thực hiện Grid Search...")
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
    
    with open(METRICS_PATH, 'w', encoding='utf-8') as f:
        f.write("=== MÔ HÌNH DỰ ĐOÁN F1 PODIUM - BÁO CÁO HIỆU SUẤT ===\n")
        f.write(f"Thời gian huấn luyện: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Bộ siêu tham số tốt nhất (Best Params): {grid_search.best_params_}\n")
        f.write(f"Độ chính xác tổng thể (Accuracy): {acc:.4f}\n")
        f.write("-" * 60 + "\n")
        f.write("Classification Report:\n")
        f.write(report)
    
    joblib.dump(best_model, MODEL_PATH)
    
    return best_model

def predict_podium_probabilities(model, current_grid_df):
    features = current_grid_df[['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']]
    probabilities = model.predict_proba(features)[:, 1]
    
    factor = 3.0 / np.sum(probabilities) if np.sum(probabilities) > 0 else 1
    current_grid_df['Podium_Probability'] = np.clip(probabilities * factor, 0, 0.99)
    
    return current_grid_df.sort_values(by='Podium_Probability', ascending=False)

# ==========================================
# Feature Extraction for Inference
# ==========================================

def prepare_race_features(year, round_num):
    print(f"\n[INFERENCE] Đang trích xuất đặc trưng cho Mùa {year} - Chặng {round_num}...")
    
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
        raise ValueError("Không thể lấy dữ liệu Vị trí xuất phát (Grid) cho chặng đua này.")

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

if __name__ == '__main__':
    model = initialize_model(force_retrain=False)
    inference_df = prepare_race_features(2024, 1)
    results_df = predict_podium_probabilities(model, inference_df)
    print(results_df[['Driver', 'GridPosition', 'Podium_Probability']].head())