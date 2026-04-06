import os
import time
import pandas as pd
import numpy as np
import fastf1
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

CACHE_DIR = 'f1_cache'
IN_RACE_DATA_PATH = os.path.join(CACHE_DIR, 'in_race_historical_data.csv')

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level('ERROR')

API_DELAY_SECONDS = 10  # Bảo vệ Rate Limit

def safe_load_race_session(year, round_num):
    attempt = 1
    while True:
        try:
            print(f" ⏳ Đang lấy dữ liệu Race: Mùa {year} - Chặng {round_num}...")
            session = fastf1.get_session(year, round_num, 'R')
            session.load(telemetry=False, weather=False, messages=False)
            time.sleep(API_DELAY_SECONDS)
            return session
        except Exception as e:
            print(f"    [!] Lỗi gọi API FastF1: {str(e)}")
            print(f"    [!] Đợi 60 giây và thử lại (Lần {attempt})...")
            time.sleep(60)
            attempt += 1

def safe_get_schedule(year):
    while True:
        try:
            schedule = fastf1.get_event_schedule(year)
            time.sleep(API_DELAY_SECONDS)
            return schedule
        except Exception as e:
            print(f"    [!] Lỗi tải lịch năm {year}: {e}. Đợi 60s...")
            time.sleep(60)

def map_compound(compound_str):
    c = str(compound_str).upper()
    if 'SOFT' in c: return 1
    if 'MEDIUM' in c: return 2
    if 'HARD' in c: return 3
    if 'INTERMEDIATE' in c: return 4
    if 'WET' in c: return 5
    return 0

def crawl_in_race_data():
    print("=" * 60)
    print("🚀 BẮT ĐẦU CÀO DỮ LIỆU IN-RACE (LAP-BY-LAP) 🚀")
    print("=" * 60)
    
    if os.path.exists(IN_RACE_DATA_PATH):
        df = pd.read_csv(IN_RACE_DATA_PATH)
        crawled_rounds = set(zip(df['Year'], df['Round']))
        print(f"[*] Tìm thấy Dataset hiện tại: {len(df)} vòng đua (laps).")
        print(f"[*] Đã cào xong {len(crawled_rounds)} chặng. Tự động bỏ qua.\n")
    else:
        df = pd.DataFrame()
        crawled_rounds = set()
        print("[*] Chưa có Dataset. Sẽ cào từ đầu (2022-nay).\n")

    start_year = 2022
    end_year = datetime.now().year

    for year in range(start_year, end_year + 1):
        schedule = safe_get_schedule(year)
        completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]

        for _, event in completed_events.iterrows():
            round_num = event['RoundNumber']
            
            if (year, round_num) in crawled_rounds:
                continue

            print(f"\n[+] ĐANG XỬ LÝ: {year} - Chặng {round_num} ({event['EventName']})")
            
            race = safe_load_race_session(year, round_num)
            laps = race.laps
            results = race.results
            
            if laps.empty or results.empty:
                print("    [!] Không có dữ liệu vòng đua. Bỏ qua.")
                continue
                
            # Tạo dictionary lưu vị trí chung cuộc
            final_positions = {}
            for _, row in results.iterrows():
                drv = row['Abbreviation']
                pos = pd.to_numeric(row['Position'], errors='coerce')
                # Nếu bỏ cuộc (DNF), gán hạng 20
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
                        'FinalPosition': final_positions[drv] # ĐÃ SỬA THÀNH FINAL POSITION
                    })

            if lap_data_list:
                new_df = pd.DataFrame(lap_data_list)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_csv(IN_RACE_DATA_PATH, index=False)
                crawled_rounds.add((year, round_num))
                print(f"  -> [OK] Đã lưu {len(new_df)} dòng dữ liệu In-Race.")

    print("\n✅ HOÀN TẤT CÀO DỮ LIỆU IN-RACE!")

if __name__ == '__main__':
    crawl_in_race_data()