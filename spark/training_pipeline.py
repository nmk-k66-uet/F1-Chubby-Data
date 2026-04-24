import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, IntegerType, FloatType, StringType
import os
import sys

is_local = sys.platform == "win32"

if is_local:
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
    os.environ['SPARK_LOCAL_IP'] = "127.0.0.1"
    os.environ["JDK_JAVA_OPTIONS"] = "--add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED"
    os.environ["HADOOP_HOME"] = "D:\\hadoop"
    os.environ["PATH"] += os.pathsep + "D:\\hadoop\\bin"

BUCKET = "f1chubby-raw-gen-lang-client-0314607994"

builder = SparkSession.builder.appName("F1_Model_Training_Pipeline")

if is_local:
    # Local Windows Testing Configurations
    builder = builder \
        .master("local[*]") \
        .config("spark.driver.host", "127.0.0.1") \
        .config("spark.driver.bindAddress", "127.0.0.1") \
        .config("spark.jars.packages", "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.22") \
        .config("spark.hadoop.fs.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem") \
        .config("spark.hadoop.fs.AbstractFileSystem.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFS") \
        .config("spark.hadoop.google.cloud.auth.service.account.enable", "true") \
        .config("spark.hadoop.google.cloud.auth.service.account.json.keyfile", "gcs-key/gen-lang-client-0314607994-ff9d436a97ef.json") \
        .config("spark.python.worker.faulthandler.enabled", "true") \
        .config("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true")

spark = builder.getOrCreate()

print("Spark Initialized Sucessfully")
# ==========================================
# 1. Define the Distributed Worker Function for Pre-Race
# ==========================================
def extract_pre_race_features(iterator):
    """
    This function runs independently on every Spark Worker node.
    It takes a batch of Years, iterates through all rounds of that year sequentially 
    (to correctly calculate DriverForm), checks GCS, loads FastF1,
    and returns a Pandas DataFrame of extracted ML features.
    """
    import os
    import fastf1
    import pandas as pd
    import numpy as np
    from datetime import datetime
    
    # Import lightweight, decoupled GCS loader
    from core.gcs_utils import get_schedule, load_with_gcs_cache
    from core.ml_core import extract_best_q_time, extract_fp2_long_run_pace, get_team_tier
    
    import uuid
    unique_cache_dir = f'f1_cache_{uuid.uuid4().hex}'
    os.makedirs(unique_cache_dir, exist_ok=True)

    def load(year, round_num, session_type, telemetry=False, weather=False, messages=False):
        return load_with_gcs_cache(year, round_num, session_type, telemetry, weather, messages, cache_dir=unique_cache_dir)
    fastf1.Cache.enable_cache(unique_cache_dir)
    fastf1.set_log_level('ERROR')
    
    for pdf in iterator:
        batch_features = []
        
        for _, row in pdf.iterrows():
            year = int(row['Year'])
            
            # Use get_schedule from data_loader
            try:
                schedule = get_schedule(year)
                if schedule.empty:
                    continue
                completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]
            except Exception as e:
                print(f"Error fetching schedule for {year}: {e}")
                continue

            driver_points = {}

            for _, event in completed_events.iterrows():
                round_num = event['RoundNumber']
                
                # 1. Tải Race Result để tính điểm Form (DriverForm)
                try:
                    race = load(year, round_num, 'R', telemetry=False, weather=False, messages=False)
                    r_results = race.results
                    
                    form_dict = {}
                    max_pts = max(1, (round_num - 1) * 26)
                    for drv in r_results['Abbreviation']:
                        form_dict[drv] = driver_points.get(drv, 0) / max_pts

                    for _, r_row in r_results.iterrows():
                        drv = r_row['Abbreviation']
                        driver_points[drv] = driver_points.get(drv, 0) + pd.to_numeric(r_row['Points'], errors='coerce')
                except Exception as e:
                    print(f"    [!] Lỗi đọc Race chặng {round_num} năm {year}: {e}")
                    continue

                # 2. Lấy Qualifying
                try:
                    qualy = load(year, round_num, 'Q', telemetry=False, weather=False, messages=False)
                    q_results = qualy.results
                    pole_time = None
                    if not q_results.empty:
                        all_q_times = q_results.apply(extract_best_q_time, axis=1).dropna()
                        if not all_q_times.empty: pole_time = all_q_times.min()
                except Exception as e:
                    q_results = pd.DataFrame()
                    pole_time = None

                # 3. Lấy Long Run Pace (FP2 or Sprint)
                format_type = event.get('EventFormat', 'conventional').lower()
                pace_session_code = 'S' if format_type in ['sprint', 'sprint_qualifying'] else 'FP2'
                fp2_deltas = {}
                try:
                    pace_session = load(year, round_num, pace_session_code, telemetry=False, weather=False, messages=False)
                    fp2_deltas = extract_fp2_long_run_pace(pace_session)
                except: 
                    pass

                # 4. Xây dựng Features
                for _, r_row in r_results.iterrows():
                    driver = r_row['Abbreviation']
                    grid_pos = pd.to_numeric(r_row['GridPosition'], errors='coerce')
                    if pd.isna(grid_pos) or grid_pos == 0: grid_pos = 20

                    tier = get_team_tier(r_row['TeamName'])

                    q_delta = 2.5
                    if not q_results.empty and driver in q_results['Abbreviation'].values:
                        driver_q = q_results[q_results['Abbreviation'] == driver].iloc[0]
                        best_q = extract_best_q_time(driver_q)
                        if best_q is not None and pole_time is not None:
                            q_delta = best_q - pole_time

                    fp2_delta = fp2_deltas.get(driver, np.nan)
                    form = form_dict.get(driver, 0.0)

                    # Lưu vị trí thực tế
                    pos = pd.to_numeric(r_row['Position'], errors='coerce')
                    final_pos = int(pos) if pd.notna(pos) else 20

                    batch_features.append({
                        'Year': year, 
                        'Round': round_num, 
                        'Driver': driver,
                        'GridPosition': int(grid_pos), 
                        'TeamTier': tier,
                        'QualifyingDelta': float(max(0, q_delta)),
                        'FP2_PaceDelta': float(fp2_delta) if pd.notna(fp2_delta) else 2.0, # default 2.0 if missing
                        'DriverForm': float(form), 
                        'FinalPosition': final_pos
                    })
                
        yield pd.DataFrame(batch_features)
# ==========================================
# 2. Define the Distributed Worker Function for In-Race
# ==========================================
def extract_in_race_features(iterator):
    import os
    import fastf1
    import pandas as pd
    import numpy as np
    from datetime import datetime
    
    # Import lightweight, decoupled GCS loader
    from core.gcs_utils import get_schedule, load_with_gcs_cache
    from core.data_crawler import map_compound
    
    import uuid
    unique_cache_dir = f'f1_cache_{uuid.uuid4().hex}'
    os.makedirs(unique_cache_dir, exist_ok=True)

    def load(year, round_num, session_type, telemetry=False, weather=False, messages=False):
        return load_with_gcs_cache(year, round_num, session_type, telemetry, weather, messages, cache_dir=unique_cache_dir)
    fastf1.Cache.enable_cache(unique_cache_dir)
    fastf1.set_log_level('ERROR')
    
    for pdf in iterator:
        batch_features = []
        for _, row in pdf.iterrows():
            year = int(row['Year'])
            
            try:
                schedule = get_schedule(year)
                if schedule.empty: continue
                completed_events = schedule[(schedule['EventDate'] < datetime.now()) & (schedule['RoundNumber'] > 0)]
            except:
                continue

            for _, event in completed_events.iterrows():
                round_num = event['RoundNumber']
                
                try:
                    race = load(year, round_num, 'R', telemetry=False, weather=False, messages=False)
                    laps = race.laps
                    results = race.results
                except Exception as e:
                    print(f"Error loading race {year} round {round_num}: {e}")
                    continue
                
                if laps.empty or results.empty:
                    continue
                    
                final_positions = {}
                for _, r_row in results.iterrows():
                    drv = r_row['Abbreviation']
                    pos = pd.to_numeric(r_row['Position'], errors='coerce')
                    final_positions[drv] = int(pos) if pd.notna(pos) else 20

                total_laps = laps['LapNumber'].max()

                for lap_num, lap_group in laps.groupby('LapNumber'):
                    valid_times = lap_group.dropna(subset=['Time'])
                    if valid_times.empty: continue
                    leader_time = valid_times['Time'].min()
                    
                    for _, l_row in lap_group.iterrows():
                        drv = l_row['Driver']
                        if drv not in final_positions: continue
                        
                        current_pos = pd.to_numeric(l_row.get('Position'), errors='coerce')
                        if pd.isna(current_pos): continue
                        
                        gap_to_leader = 0.0
                        if pd.notna(l_row.get('Time')):
                            gap_to_leader = (l_row['Time'] - leader_time).total_seconds()
                        
                        tyre_life = pd.to_numeric(l_row.get('TyreLife'), errors='coerce')
                        if pd.isna(tyre_life): tyre_life = 1.0
                        compound_idx = map_compound(l_row.get('Compound'))
                        is_pit_out = 1 if pd.notna(l_row.get('PitOutTime')) else 0
                        
                        batch_features.append({
                            'Year': year,
                            'Round': round_num,
                            'Driver': drv,
                            'LapNumber': int(lap_num),
                            'LapFraction': float(lap_num / total_laps) if total_laps else 0.0,
                            'CurrentPosition': int(current_pos),
                            'GapToLeader': float(gap_to_leader),
                            'TyreLife': float(tyre_life),
                            'CompoundIdx': int(compound_idx),
                            'IsPitOut': int(is_pit_out),
                            'FinalPosition': final_positions[drv]
                        })
                        
        yield pd.DataFrame(batch_features)
# ==========================================
# 3. Distribute the Workload across Spark
# ==========================================
# Create a list of years you want to process (e.g., 2022 to 2025)
# By distributing by Year, the worker can correctly accumulate the DriverForm sequentially
years = [(2022,), (2023,), (2024,), (2025,)]

# Define the Spark schema for the output features
schema_pre_race = StructType([
    StructField("Year", IntegerType(), True),
    StructField("Round", IntegerType(), True),
    StructField("Driver", StringType(), True),
    StructField("GridPosition", IntegerType(), True),
    StructField("TeamTier", IntegerType(), True),
    StructField("QualifyingDelta", FloatType(), True),
    StructField("FP2_PaceDelta", FloatType(), True),
    StructField("DriverForm", FloatType(), True),
    StructField("FinalPosition", IntegerType(), True)
])

# Create the work queue DataFrame
df_years = spark.createDataFrame(years, ["Year"])

# Repartition to distribute each year to a different worker
df_years = df_years.repartition(4)

# Run the distributed extraction
df_pre_race_features = df_years.mapInPandas(extract_pre_race_features, schema=schema_pre_race)

# Save these distributed features to a single file in GCS by coalescing to 1 partition
df_pre_race_features.coalesce(1).write.mode("overwrite").csv(f"gs://{BUCKET}/processed_features/pre_race_features", header=True)

# df_pre_race_features.coalesce(1).write.mode("overwrite").csv("./local_test_output/pre_race_features", header=True)

schema_in_race = StructType([
    StructField("Year", IntegerType(), True),
    StructField("Round", IntegerType(), True),
    StructField("Driver", StringType(), True),
    StructField("LapNumber", IntegerType(), True),
    StructField("LapFraction", FloatType(), True),
    StructField("CurrentPosition", IntegerType(), True),
    StructField("GapToLeader", FloatType(), True),
    StructField("TyreLife", FloatType(), True),
    StructField("CompoundIdx", IntegerType(), True),
    StructField("IsPitOut", IntegerType(), True),
    StructField("FinalPosition", IntegerType(), True)
])

df_in_race_features = df_years.mapInPandas(extract_in_race_features, schema=schema_in_race)


# Save these distributed features to a single file in GCS by coalescing to 1 partition
# df_in_race_features.coalesce(1).write.mode("overwrite").csv(f"gs://{BUCKET}/processed_features/in_race_features_csv", header=True)
df_in_race_features.coalesce(1).write.mode("overwrite").csv(f"gs://{BUCKET}/processed_features/in_race_features", header=True)
