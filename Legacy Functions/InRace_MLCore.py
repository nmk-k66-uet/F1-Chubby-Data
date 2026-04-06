import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import classification_report, accuracy_score
import joblib

CACHE_DIR = 'f1_cache'
IN_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'in_race_historical_data.csv')

# Lưu riêng 2 model
IN_RACE_WIN_MODEL_PATH = os.path.join(CACHE_DIR, 'in_race_win_model.pkl')
IN_RACE_PODIUM_MODEL_PATH = os.path.join(CACHE_DIR, 'in_race_podium_model.pkl')
METRICS_PATH = os.path.join(CACHE_DIR, 'in_race_metrics.txt')

def train_in_race_model(force_retrain=False):
    """Huấn luyện song song mô hình Win và Podium dựa trên dữ liệu Lap-by-Lap"""
    
    if not force_retrain and os.path.exists(IN_RACE_WIN_MODEL_PATH) and os.path.exists(IN_RACE_PODIUM_MODEL_PATH):
        print("[ML] Đã tìm thấy các In-Race Models cache. Đang nạp...")
        return joblib.load(IN_RACE_WIN_MODEL_PATH), joblib.load(IN_RACE_PODIUM_MODEL_PATH)
        
    print("[ML] Bắt đầu huấn luyện In-Race Models (Win & Podium)...")
    
    if not os.path.exists(IN_RACE_DATA_PATH):
        raise FileNotFoundError(f"Không tìm thấy file {IN_RACE_DATA_PATH}. Vui lòng chạy InRace_DataCrawler.py trước!")
        
    df = pd.read_csv(IN_RACE_DATA_PATH)
    df = df.dropna(subset=['CurrentPosition', 'GapToLeader', 'TyreLife'])
    
    print(f"[ML] Kích thước tập dữ liệu huấn luyện: {len(df)} vòng đua.")
    
    X = df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
    
    # Tạo 2 Target Variables
    y_win = (df['FinalPosition'] == 1).astype(int)
    y_podium = (df['FinalPosition'] <= 3).astype(int)
    
    # Chia test set, ưu tiên stratify theo Podium để cân bằng
    X_train, X_test, y_train_w, y_test_w, y_train_p, y_test_p = train_test_split(
        X, y_win, y_podium, test_size=0.2, random_state=42, stratify=y_podium
    )
    
    param_dist = {
        'n_estimators': [100, 150],
        'max_depth': [8, 12, 15],
        'min_samples_split': [5, 10]
    }
    
    print("[ML] Đang huấn luyện WIN Predictor Model...")
    base_win = RandomForestClassifier(random_state=42, class_weight='balanced')
    search_win = RandomizedSearchCV(estimator=base_win, param_distributions=param_dist, 
                                n_iter=5, cv=3, scoring='f1', n_jobs=-1, verbose=1, random_state=42)
    search_win.fit(X_train, y_train_w)
    best_win = search_win.best_estimator_
    
    print("[ML] Đang huấn luyện PODIUM Predictor Model...")
    base_pod = RandomForestClassifier(random_state=42, class_weight='balanced')
    search_pod = RandomizedSearchCV(estimator=base_pod, param_distributions=param_dist, 
                                n_iter=5, cv=3, scoring='f1', n_jobs=-1, verbose=1, random_state=42)
    search_pod.fit(X_train, y_train_p)
    best_pod = search_pod.best_estimator_
    
    # Đánh giá Metrics
    acc_w = accuracy_score(y_test_w, best_win.predict(X_test))
    rep_w = classification_report(y_test_w, best_win.predict(X_test))
    
    acc_p = accuracy_score(y_test_p, best_pod.predict(X_test))
    rep_p = classification_report(y_test_p, best_pod.predict(X_test))
    
    with open(METRICS_PATH, 'w', encoding='utf-8') as f:
        f.write("=== IN-RACE MODEL METRICS ===\n\n")
        f.write("--- WIN MODEL ---\n")
        f.write(f"Bộ tham số: {search_win.best_params_}\n")
        f.write(f"Độ chính xác (Accuracy): {acc_w:.4f}\n")
        f.write(rep_w + "\n\n")
        
        f.write("--- PODIUM MODEL ---\n")
        f.write(f"Bộ tham số: {search_pod.best_params_}\n")
        f.write(f"Độ chính xác (Accuracy): {acc_p:.4f}\n")
        f.write(rep_p + "\n")
        
    joblib.dump(best_win, IN_RACE_WIN_MODEL_PATH)
    joblib.dump(best_pod, IN_RACE_PODIUM_MODEL_PATH)
    
    print("[ML] Huấn luyện thành công cả 2 mô hình!")
    return best_win, best_pod

def predict_live_lap(models, live_lap_df):
    """Tính toán và trả về song song Tỉ lệ Win và Podium"""
    win_model, podium_model = models
    features = live_lap_df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
    
    # Lấy mảng xác suất cột 1 (class = 1)
    prob_win = win_model.predict_proba(features)[:, 1]
    prob_pod = podium_model.predict_proba(features)[:, 1]
    
    # Ép tổng Win = 100% (1 người), Podium = 300% (3 người)
    factor_w = 1.0 / np.sum(prob_win) if np.sum(prob_win) > 0 else 1
    factor_p = 3.0 / np.sum(prob_pod) if np.sum(prob_pod) > 0 else 1
    
    live_lap_df['Live_Win_Prob'] = np.clip(prob_win * factor_w, 0, 0.99)
    live_lap_df['Live_Podium_Prob'] = np.clip(prob_pod * factor_p, 0, 0.99)
    
    # Ép chuẩn logic: Xác suất vô địch không được phép lớn hơn xác suất lên bục
    live_lap_df['Live_Win_Prob'] = np.minimum(live_lap_df['Live_Win_Prob'], live_lap_df['Live_Podium_Prob'])
    
    # Ưu tiên xếp hạng theo Tỉ lệ vô địch, nếu bằng nhau thì xét tới Tỉ lệ Podium
    return live_lap_df.sort_values(by=['Live_Win_Prob', 'Live_Podium_Prob'], ascending=[False, False])

if __name__ == '__main__':
    # Chạy trực tiếp file này để huấn luyện
    train_in_race_model(force_retrain=True)