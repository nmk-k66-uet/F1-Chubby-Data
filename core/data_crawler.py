"""Data Crawler Module - Historical F1 Data Collection

Collects historical F1 race data from FastF1 API for training ML models:
- Pre-race data: Grid positions, qualifying times, practice performance
- In-race data: Lap times, lap positions, race progress
- Handles API rate limiting and connection errors with automatic retries

Data is cached locally to f1_cache directory and processed into CSV files.
"""

import os
import time
import pandas as pd
import numpy as np
import fastf1
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

CACHE_DIR = 'f1_cache'
PRE_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'pre_race_historical_data.csv')
IN_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'in_race_historical_data.csv')

API_DELAY_SECONDS = 10

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

# ==========================================
# Utility Functions
# ==========================================
def safe_load_session(year, round_num, session_code):
    """Load FastF1 session data with automatic retry on API failures.
    
    Implements exponential backoff with 60-second delays between retries
    when FastF1 API calls fail.
    
    Args:
        year (int): Season year (e.g., 2026, 2025).
        round_num (int): Round number of the race.
        session_code (str): Session code ('FP1', 'FP2', 'FP3', 'Q', 'S', 'R').
    
    Returns:
        fastf1.core.Session: Loaded session object with race data.
    
    Output: Prints progress messages and error logs with retry attempts.
    """
    attempt = 1
    while True:
        try:
            print(f" ⏳ Đang tải dữ liệu: Mùa {year} - Chặng {round_num} [{session_code}]...")
            session = fastf1.get_session(year, round_num, session_code)
            session.load(telemetry=False, weather=False, messages=False)
            time.sleep(API_DELAY_SECONDS)
            return session
        except Exception as e:
            print(f"    [!] Lỗi gọi API FastF1: {str(e)}")
            print(f"    [!] Đợi 60 giây và thử lại (Lần {attempt})...")
            time.sleep(60)
            attempt += 1

def safe_get_schedule(year):
    """Fetch F1 season calendar with automatic retry on API failures.
    
    Args:
        year (int): Season year (e.g., 2026, 2025).
    
    Returns:
        pd.DataFrame: Season schedule with all races and dates.
    
    Output: Prints error logs with retry attempts if API fails.
    """
    while True:
        try:
            schedule = fastf1.get_event_schedule(year)
            time.sleep(API_DELAY_SECONDS)
            return schedule
        except Exception as e:
            print(f"    [!] Lỗi tải lịch năm {year}: {e}. Đợi 60s...")
            time.sleep(60)

def get_team_tier(team_name):
    team_str = str(team_name).lower()
    t1 = ['red bull', 'ferrari', 'mclaren', 'mercedes']
    t2 = ['aston martin', 'alpine', 'rb', 'alphatauri', 'racing point']
    if any(t in team_str for t in t1): return 1
    if any(t in team_str for t in t2): return 2
    return 3

def map_compound(compound_str):
    c = str(compound_str).upper()
    if 'SOFT' in c: return 1
    if 'MEDIUM' in c: return 2
    if 'HARD' in c: return 3
    if 'INTERMEDIATE' in c: return 4
    if 'WET' in c: return 5
    return 0

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
# MODULE 1: PRE-RACE DATA CRAWLER
# ==========================================
def crawl_pre_race_data():
    print("=" * 60)
    print("BẮT ĐẦU TẢI DỮ LIỆU PRE-RACE (Dự đoán Trước chặng) 🚀")
    print("=" * 60)
    
    if os.path.exists(PRE_RACE_DATA_PATH):
        df = pd.read_csv(PRE_RACE_DATA_PATH)
        crawled_rounds = set(zip(df['Year'], df['Round']))
        print(f"[*] Tìm thấy Dataset hiện tại: {len(df)} bản ghi.")
        print(f"[*] Đã tải xong {len(crawled_rounds)} chặng. Tự động bỏ qua.\n")
    else:
        df = pd.DataFrame()
        crawled_rounds = set()
        print("[*] Chưa có Dataset. Sẽ tải từ đầu (2022-nay).\n")

    start_year = 2022
    end_year = datetime.now().year

    for year in range(start_year, end_year + 1):
        schedule = safe_get_schedule(year)
        completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]

        driver_points = {}

        for _, event in completed_events.iterrows():
            round_num = event['RoundNumber']
            event_name = event['EventName']

            # Tải Race Result để tính điểm Form
            try:
                race = safe_load_session(year, round_num, 'R')
                r_results = race.results
                
                form_dict = {}
                max_pts = max(1, (round_num - 1) * 26)
                for drv in r_results['Abbreviation']:
                    form_dict[drv] = driver_points.get(drv, 0) / max_pts

                for _, row in r_results.iterrows():
                    drv = row['Abbreviation']
                    driver_points[drv] = driver_points.get(drv, 0) + pd.to_numeric(row['Points'], errors='coerce')
            except Exception as e:
                print(f"    [!] Lỗi đọc Race chặng {round_num} năm {year}: {e}")
                continue

            if (year, round_num) in crawled_rounds:
                continue

            print(f"\n[PRE-RACE] Đang tải dữ liệu: {year} - Chặng {round_num} ({event_name})...")
            round_data = []
            
            try:
                # Lấy Qualifying
                qualy = safe_load_session(year, round_num, 'Q')
                q_results = qualy.results
                pole_time = None
                if not q_results.empty:
                    all_q_times = q_results.apply(extract_best_q_time, axis=1).dropna()
                    if not all_q_times.empty: pole_time = all_q_times.min()

                # Lấy Long Run Pace
                format_type = event.get('EventFormat', 'conventional').lower()
                pace_session_code = 'S' if format_type in ['sprint', 'sprint_qualifying'] else 'FP2'
                fp2_deltas = {}
                try:
                    pace_session = safe_load_session(year, round_num, pace_session_code)
                    fp2_deltas = extract_fp2_long_run_pace(pace_session)
                except: pass

                # Xây dựng Features
                for _, row in r_results.iterrows():
                    driver = row['Abbreviation']
                    grid_pos = pd.to_numeric(row['GridPosition'], errors='coerce')
                    if pd.isna(grid_pos) or grid_pos == 0: grid_pos = 20

                    tier = get_team_tier(row['TeamName'])

                    q_delta = 2.5
                    if not q_results.empty and driver in q_results['Abbreviation'].values:
                        driver_q = q_results[q_results['Abbreviation'] == driver].iloc[0]
                        best_q = extract_best_q_time(driver_q)
                        if best_q is not None and pole_time is not None:
                            q_delta = best_q - pole_time

                    fp2_delta = fp2_deltas.get(driver, np.nan)
                    form = form_dict.get(driver, 0.0)

                    # Lưu vị trí thực tế để train Win/Podium Model
                    pos = pd.to_numeric(row['Position'], errors='coerce')
                    final_pos = int(pos) if pd.notna(pos) else 20

                    round_data.append({
                        'Year': year, 'Round': round_num, 'Driver': driver,
                        'GridPosition': int(grid_pos), 'TeamTier': tier,
                        'QualifyingDelta': float(max(0, q_delta)),
                        'FP2_PaceDelta': fp2_delta,
                        'DriverForm': float(form), 
                        'FinalPosition': final_pos
                    })

                if round_data:
                    new_df = pd.DataFrame(round_data)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(PRE_RACE_DATA_PATH, index=False)
                    crawled_rounds.add((year, round_num))
                    print(f"  -> [OK] Pre-Race lưu thành công.")

            except Exception as e:
                print(f"  -> [ERROR] Lỗi xây dựng features: {e}")

# ==========================================
# MODULE 2: IN-RACE DATA CRAWLER
# ==========================================
def crawl_in_race_data():
    print("\n" + "=" * 60)
    print("BẮT ĐẦU TẢI DỮ LIỆU IN-RACE (Dự đoán Lap-by-Lap) 🚀")
    print("=" * 60)
    
    if os.path.exists(IN_RACE_DATA_PATH):
        df = pd.read_csv(IN_RACE_DATA_PATH)
        crawled_rounds = set(zip(df['Year'], df['Round']))
        print(f"[*] Tìm thấy Dataset hiện tại: {len(df)} vòng đua (laps).")
        print(f"[*] Đã tải xong {len(crawled_rounds)} chặng. Tự động bỏ qua.\n")
    else:
        df = pd.DataFrame()
        crawled_rounds = set()
        print("[*] Chưa có Dataset. Sẽ tải từ đầu (2022-nay).\n")

    start_year = 2022
    end_year = datetime.now().year

    for year in range(start_year, end_year + 1):
        schedule = safe_get_schedule(year)
        completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]

        for _, event in completed_events.iterrows():
            round_num = event['RoundNumber']
            
            if (year, round_num) in crawled_rounds:
                continue

            print(f"\n[IN-RACE] ĐANG XỬ LÝ: {year} - Chặng {round_num} ({event['EventName']})")
            
            race = safe_load_session(year, round_num, 'R')
            laps = race.laps
            results = race.results
            
            if laps.empty or results.empty:
                print("    [!] Không có dữ liệu vòng đua. Bỏ qua.")
                continue
                
            final_positions = {}
            for _, row in results.iterrows():
                drv = row['Abbreviation']
                pos = pd.to_numeric(row['Position'], errors='coerce')
                final_positions[drv] = int(pos) if pd.notna(pos) else 20

            total_laps = laps['LapNumber'].max()
            lap_data_list = []

            for lap_num, lap_group in laps.groupby('LapNumber'):
                valid_times = lap_group.dropna(subset=['Time'])
                if valid_times.empty: continue
                leader_time = valid_times['Time'].min()
                
                for _, row in lap_group.iterrows():
                    drv = row['Driver']
                    if drv not in final_positions: continue
                    
                    current_pos = pd.to_numeric(row.get('Position'), errors='coerce')
                    if pd.isna(current_pos): continue
                    
                    gap_to_leader = 0.0
                    if pd.notna(row['Time']):
                        gap_to_leader = (row['Time'] - leader_time).total_seconds()
                    
                    tyre_life = pd.to_numeric(row.get('TyreLife'), errors='coerce')
                    if pd.isna(tyre_life): tyre_life = 1.0
                    compound_idx = map_compound(row.get('Compound'))
                    is_pit_out = 1 if pd.notna(row.get('PitOutTime')) else 0
                    
                    lap_data_list.append({
                        'Year': year,
                        'Round': round_num,
                        'Driver': drv,
                        'LapNumber': int(lap_num),
                        'LapFraction': float(lap_num / total_laps),
                        'CurrentPosition': int(current_pos),
                        'GapToLeader': float(gap_to_leader),
                        'TyreLife': float(tyre_life),
                        'CompoundIdx': compound_idx,
                        'IsPitOut': is_pit_out,
                        'FinalPosition': final_positions[drv]
                    })

            if lap_data_list:
                new_df = pd.DataFrame(lap_data_list)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_csv(IN_RACE_DATA_PATH, index=False)
                crawled_rounds.add((year, round_num))
                print(f"  -> [OK] Đã lưu {len(new_df)} dòng dữ liệu In-Race.")

if __name__ == '__main__':
    print("ĐANG KHỞI ĐỘNG HỆ THỐNG THU THẬP DỮ LIỆU ...")
    crawl_pre_race_data()
    crawl_in_race_data()
    print("\n✅ TẤT CẢ QUÁ TRÌNH TẢI DỮ LIỆU ĐÃ HOÀN TẤT!")