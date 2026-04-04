import os
import time
import pandas as pd
import numpy as np
import fastf1
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

CACHE_DIR = 'f1_cache'
DATA_PATH = os.path.join(CACHE_DIR, 'historical_data_v2.csv')

API_DELAY_SECONDS = 15  

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

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

def crawl_data():
    print("=" * 60)
    print("Starting Data Crawler")
    print("=" * 60)
    
    # Check for existing data to enable auto-resume
    if os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH)
        crawled_rounds = set(zip(df['Year'], df['Round']))
        print(f"[*] Found {len(df)} records.")
        print(f"[*] Already crawled {len(crawled_rounds)} rounds. Will automatically skip these.\n")
    else:
        df = pd.DataFrame()
        crawled_rounds = set()
        print("[*] No existing data found. Starting crawl from scratch.\n")

    start_year = 2022
    end_year = datetime.now().year

    for year in range(start_year, end_year + 1):
        try:
            schedule = fastf1.get_event_schedule(year)
            completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]
        except:
            continue

        driver_points = {}

        for _, event in completed_events.iterrows():
            round_num = event['RoundNumber']
            event_name = event['EventName']

            # 1. Race Results & Form Calculation
            try:
                race = fastf1.get_session(year, round_num, 'R')
                race.load(telemetry=False, weather=False, messages=False)
                r_results = race.results
                
                form_dict = {}
                max_pts = max(1, (round_num - 1) * 26)
                for drv in r_results['Abbreviation']:
                    form_dict[drv] = driver_points.get(drv, 0) / max_pts

                for _, row in r_results.iterrows():
                    drv = row['Abbreviation']
                    driver_points[drv] = driver_points.get(drv, 0) + pd.to_numeric(row['Points'], errors='coerce')
            except Exception as e:
                print(f"[!] Error loading Race round {round_num} year {year}: {e}")
                continue

            # 2. AUTO-RESUME CHECK
            if (year, round_num) in crawled_rounds:
                print(f"[SKIP] Already have data: {year} - Round {round_num} ({event_name})")
                continue

            # 3. Crawl Qualifying, FP2, and Build Dataset
            print(f"\n[CRAWL] Loading data: {year} - Round {round_num} ({event_name})...")
            round_data = []
            
            try:
                # Qualifying
                qualy = fastf1.get_session(year, round_num, 'Q')
                qualy.load(telemetry=False, weather=False, messages=False)
                q_results = qualy.results
                pole_time = None
                if not q_results.empty:
                    all_q_times = q_results.apply(extract_best_q_time, axis=1).dropna()
                    if not all_q_times.empty: pole_time = all_q_times.min()

                # FP2 Long Run Pace
                fp2_deltas = {}
                try:
                    fp2 = fastf1.get_session(year, round_num, 'FP2')
                    fp2_deltas = extract_fp2_long_run_pace(fp2)
                except: pass

                # Features Extraction
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

                    pos = pd.to_numeric(row['Position'], errors='coerce')
                    is_podium = 1 if pd.notna(pos) and pos <= 3 else 0

                    round_data.append({
                        'Year': year, 'Round': round_num, 'Driver': driver,
                        'GridPosition': int(grid_pos), 'TeamTier': tier,
                        'QualifyingDelta': float(max(0, q_delta)),
                        'FP2_PaceDelta': fp2_delta,
                        'DriverForm': float(form), 'Podium': is_podium
                    })

                # Save after each round
                if round_data:
                    new_df = pd.DataFrame(round_data)
                    df = pd.concat([df, new_df], ignore_index=True)
                    df.to_csv(DATA_PATH, index=False)
                    crawled_rounds.add((year, round_num))
                    
                    print(f"  -> [OK] Saved successfully. Pausing {API_DELAY_SECONDS}s ...")
                    time.sleep(API_DELAY_SECONDS)

            except Exception as e:
                print(f"  -> [ERROR] Error occurred while crawling: {e}")
                time.sleep(API_DELAY_SECONDS)

    print("\n✅ Data crawling completed.")

if __name__ == '__main__':
    crawl_data()