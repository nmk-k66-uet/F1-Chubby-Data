#!/usr/bin/env python3
"""
F1 Feature Extraction Job - Reads FastF1 cache from GCS and extracts features

This job:
1. Reads pre-cached FastF1 data from GCS (NO API CALLS)
2. Extracts pre-race and in-race features in parallel
3. Saves features to GCS as CSV for model training

Usage:
    spark-submit --py-files core.zip feature_extraction_job.py <PROJECT_ID>
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, IntegerType, FloatType, StringType
)

# Parse Project ID
if len(sys.argv) > 1:
    PROJECT_ID = sys.argv[1]
else:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "default-project-id")

RAW_BUCKET = f"f1chubby-raw-{PROJECT_ID}"

print(f"[CONFIG] Project ID: {PROJECT_ID}")
print(f"[CONFIG] Raw Bucket: gs://{RAW_BUCKET}")

# Initialize Spark
spark = SparkSession.builder.appName("F1_Feature_Extraction").getOrCreate()
print(f"[SPARK] Initialized: {spark.sparkContext.master}")

# ==========================================
# Pre-Race Feature Extractor
# ==========================================

def extract_pre_race_features(iterator):
    """
    Extract pre-race features from cached FastF1 data.
    Runs on each Spark worker, processing one year sequentially.
    """
    import os
    import fastf1
    import pandas as pd
    import numpy as np
    from datetime import datetime
    import uuid
    from google.cloud import storage

    from core.gcs_utils import get_schedule
    from core.ml_core import extract_best_q_time, extract_fp2_long_run_pace, get_team_tier

    # Create unique cache dir per worker
    cache_dir = f"/tmp/f1_cache_{uuid.uuid4().hex}"
    os.makedirs(cache_dir, exist_ok=True)

    # Initialize GCS client and list all blobs once
    print(f"[WORKER] Initializing GCS cache download to {cache_dir}...")
    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(RAW_BUCKET)
        all_blobs = list(bucket.list_blobs())
        print(f"[WORKER] Found {len(all_blobs)} objects in GCS")

        # Download SQLite database once (needed for all years)
        sqlite_downloaded = False
        for blob in all_blobs:
            if 'fastf1_http_cache.sqlite' in blob.name:
                local_path = os.path.join(cache_dir, blob.name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                blob.download_to_filename(local_path)
                print(f"[WORKER] ✓ Downloaded SQLite cache: {blob.name}")
                sqlite_downloaded = True
                break

        if not sqlite_downloaded:
            print(f"[WORKER] WARNING: SQLite cache not found in GCS")
    except Exception as e:
        print(f"[WORKER] Cache initialization error: {e}")
        all_blobs = []

    fastf1.Cache.enable_cache(cache_dir)
    fastf1.set_log_level("ERROR")

    for pdf in iterator:
        batch_features = []

        for _, row in pdf.iterrows():
            year = int(row["Year"])

            # Download only this year's .ff1pkl files
            print(f"[PRE-RACE] Downloading cache for {year}...")
            try:
                downloaded = 0
                for blob in all_blobs:
                    if blob.name.startswith(f"{year}/") and blob.name.endswith('.ff1pkl'):
                        local_path = os.path.join(cache_dir, blob.name)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        blob.download_to_filename(local_path)
                        downloaded += 1
                print(f"[PRE-RACE] Downloaded {downloaded} cache files for {year}")
            except Exception as e:
                print(f"[PRE-RACE] Cache download error for {year}: {e}")

            # Get schedule
            try:
                schedule = get_schedule(year)
                if schedule.empty:
                    print(f"[PRE-RACE] No schedule for {year}")
                    continue
                completed_events = schedule[
                    (schedule["EventDate"] < datetime.now())
                    & (schedule["RoundNumber"] > 0)
                ]
                print(f"[PRE-RACE] Year {year}: {len(completed_events)} events")
            except Exception as e:
                print(f"[PRE-RACE] Schedule error {year}: {e}")
                continue

            driver_points = {}

            for _, event in completed_events.iterrows():
                round_num = event["RoundNumber"]

                # Load Race for DriverForm calculation
                try:
                    race = fastf1.get_session(year, round_num, 'R')
                    race.load(telemetry=False, weather=False, messages=False)
                    r_results = race.results

                    if r_results.empty:
                        raise ValueError(f"Empty results {year} R{round_num}")

                    # Calculate DriverForm BEFORE race
                    max_pts = max(1, (round_num - 1) * 26)
                    form_dict = {}
                    for drv in r_results["Abbreviation"]:
                        form_dict[drv] = driver_points.get(drv, 0) / max_pts

                    # Update points AFTER form calculation
                    for _, r_row in r_results.iterrows():
                        drv = r_row["Abbreviation"]
                        driver_points[drv] = driver_points.get(drv, 0) + pd.to_numeric(
                            r_row["Points"], errors="coerce"
                        )
                except Exception as e:
                    print(f"[PRE-RACE] Error loading Race {year} R{round_num}: {e}")
                    continue

                # Load Qualifying
                try:
                    qualy = fastf1.get_session(year, round_num, 'Q')
                    qualy.load(telemetry=False, weather=False, messages=False)
                    q_results = qualy.results
                    pole_time = None
                    if not q_results.empty:
                        all_q_times = q_results.apply(extract_best_q_time, axis=1).dropna()
                        if not all_q_times.empty:
                            pole_time = all_q_times.min()
                except Exception as e:
                    print(f"[PRE-RACE] Error loading Qualifying {year} R{round_num}: {e}")
                    q_results = pd.DataFrame()
                    pole_time = None

                # Load FP2/Sprint for pace
                format_type = event.get('EventFormat', 'conventional').lower()
                pace_session_code = 'S' if format_type in ['sprint', 'sprint_qualifying'] else 'FP2'
                fp2_deltas = {}
                try:
                    pace_session = fastf1.get_session(year, round_num, pace_session_code)
                    fp2_deltas = extract_fp2_long_run_pace(pace_session)
                except Exception as e:
                    print(f"[PRE-RACE] Error loading {pace_session_code} {year} R{round_num}: {e}")

                # Build features per driver
                drivers_processed = 0
                for _, r_row in r_results.iterrows():
                    driver = r_row["Abbreviation"]
                    grid_pos = pd.to_numeric(r_row["GridPosition"], errors="coerce")
                    if pd.isna(grid_pos) or grid_pos == 0:
                        grid_pos = 20

                    tier = get_team_tier(r_row["TeamName"])

                    q_delta = 2.5
                    if not q_results.empty and driver in q_results["Abbreviation"].values:
                        driver_q = q_results[q_results["Abbreviation"] == driver].iloc[0]
                        best_q = extract_best_q_time(driver_q)
                        if best_q is not None and pole_time is not None:
                            q_delta = best_q - pole_time

                    fp2_delta = fp2_deltas.get(driver, np.nan)
                    form = form_dict.get(driver, 0.0)

                    pos = pd.to_numeric(r_row["Position"], errors="coerce")
                    is_podium = 1 if pd.notna(pos) and pos <= 3 else 0

                    batch_features.append({
                        "Year": year,
                        "Round": round_num,
                        "Driver": driver,
                        "GridPosition": int(grid_pos),
                        "TeamTier": tier,
                        "QualifyingDelta": float(max(0, q_delta)),
                        "FP2_PaceDelta": float(fp2_delta) if pd.notna(fp2_delta) else np.nan,
                        "DriverForm": float(form),
                        "Podium": is_podium,
                    })
                    drivers_processed += 1

                print(f"[PRE-RACE] ✓ {year} R{round_num}: {drivers_processed} drivers")

        print(f"[PRE-RACE] Worker completed: {len(batch_features)} features")
        yield pd.DataFrame(batch_features)


# ==========================================
# In-Race Feature Extractor
# ==========================================

def extract_in_race_features(iterator):
    """
    Extract in-race lap-by-lap features from cached FastF1 data.
    Runs on each Spark worker, processing one year sequentially.
    """
    import os
    import fastf1
    import pandas as pd
    import numpy as np
    from datetime import datetime
    import uuid
    from google.cloud import storage

    from core.gcs_utils import get_schedule
    from core.data_crawler import map_compound

    cache_dir = f"/tmp/f1_cache_{uuid.uuid4().hex}"
    os.makedirs(cache_dir, exist_ok=True)

    # Initialize GCS client and list all blobs once
    print(f"[WORKER] Initializing GCS cache download to {cache_dir}...")
    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(RAW_BUCKET)
        all_blobs = list(bucket.list_blobs())
        print(f"[WORKER] Found {len(all_blobs)} objects in GCS")

        # Download SQLite database once (needed for all years)
        sqlite_downloaded = False
        for blob in all_blobs:
            if 'fastf1_http_cache.sqlite' in blob.name:
                local_path = os.path.join(cache_dir, blob.name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                blob.download_to_filename(local_path)
                print(f"[WORKER] ✓ Downloaded SQLite cache: {blob.name}")
                sqlite_downloaded = True
                break

        if not sqlite_downloaded:
            print(f"[WORKER] WARNING: SQLite cache not found in GCS")
    except Exception as e:
        print(f"[WORKER] Cache initialization error: {e}")
        all_blobs = []

    fastf1.Cache.enable_cache(cache_dir)
    fastf1.set_log_level("ERROR")

    for pdf in iterator:
        batch_features = []

        for _, row in pdf.iterrows():
            year = int(row["Year"])

            # Download only this year's .ff1pkl files
            print(f"[IN-RACE] Downloading cache for {year}...")
            try:
                downloaded = 0
                for blob in all_blobs:
                    if blob.name.startswith(f"{year}/") and blob.name.endswith('.ff1pkl'):
                        local_path = os.path.join(cache_dir, blob.name)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        blob.download_to_filename(local_path)
                        downloaded += 1
                print(f"[IN-RACE] Downloaded {downloaded} cache files for {year}")
            except Exception as e:
                print(f"[IN-RACE] Cache download error for {year}: {e}")

            try:
                schedule = get_schedule(year)
                if schedule.empty:
                    print(f"[IN-RACE] No schedule for {year}")
                    continue
                completed_events = schedule[
                    (schedule["EventDate"] < datetime.now())
                    & (schedule["RoundNumber"] > 0)
                ]
                print(f"[IN-RACE] Year {year}: {len(completed_events)} events")
            except Exception as e:
                print(f"[IN-RACE] Schedule error {year}: {e}")
                continue

            for _, event in completed_events.iterrows():
                round_num = event["RoundNumber"]

                try:
                    race = fastf1.get_session(year, round_num, 'R')
                    race.load(telemetry=False, weather=False, messages=False)
                    laps = race.laps
                    results = race.results

                    if laps.empty or results.empty:
                        raise ValueError(f"Empty data {year} R{round_num}")

                except Exception as e:
                    print(f"[IN-RACE] Error loading {year} R{round_num}: {e}")
                    continue

                print(f"[IN-RACE] {year} R{round_num}: {len(laps)} laps")

                # Build final position lookup
                final_positions = {}
                for _, r_row in results.iterrows():
                    drv = r_row["Abbreviation"]
                    pos = pd.to_numeric(r_row["Position"], errors="coerce")
                    final_positions[drv] = int(pos) if pd.notna(pos) else 20

                total_laps = laps["LapNumber"].max()

                # Process each lap
                for lap_num, lap_group in laps.groupby("LapNumber"):
                    valid_times = lap_group.dropna(subset=["Time"])
                    if valid_times.empty:
                        continue
                    leader_time = valid_times["Time"].min()

                    for _, l_row in lap_group.iterrows():
                        drv = l_row["Driver"]
                        if drv not in final_positions:
                            continue

                        current_pos = pd.to_numeric(l_row.get("Position"), errors="coerce")
                        if pd.isna(current_pos):
                            continue

                        gap_to_leader = 0.0
                        if pd.notna(l_row.get("Time")):
                            gap_to_leader = (l_row["Time"] - leader_time).total_seconds()

                        tyre_life = pd.to_numeric(l_row.get("TyreLife"), errors="coerce")
                        if pd.isna(tyre_life):
                            tyre_life = 1.0
                        compound_idx = map_compound(l_row.get("Compound"))
                        is_pit_out = 1 if pd.notna(l_row.get("PitOutTime")) else 0

                        batch_features.append({
                            "Year": year,
                            "Round": round_num,
                            "Driver": drv,
                            "LapNumber": int(lap_num),
                            "LapFraction": float(lap_num / total_laps) if total_laps else 0.0,
                            "CurrentPosition": int(current_pos),
                            "GapToLeader": float(gap_to_leader),
                            "TyreLife": float(tyre_life),
                            "CompoundIdx": int(compound_idx),
                            "IsPitOut": int(is_pit_out),
                            "FinalPosition": final_positions[drv],
                        })

        print(f"[IN-RACE] Worker completed: {len(batch_features)} laps")
        yield pd.DataFrame(batch_features)


# ==========================================
# Spark Schemas
# ==========================================

schema_pre_race = StructType([
    StructField("Year", IntegerType(), True),
    StructField("Round", IntegerType(), True),
    StructField("Driver", StringType(), True),
    StructField("GridPosition", IntegerType(), True),
    StructField("TeamTier", IntegerType(), True),
    StructField("QualifyingDelta", FloatType(), True),
    StructField("FP2_PaceDelta", FloatType(), True),
    StructField("DriverForm", FloatType(), True),
    StructField("Podium", IntegerType(), True)
])

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

# ==========================================
# Execution
# ==========================================

# Years to process
years = [(2022,), (2023,), (2024,), (2025,)]
df_years = spark.createDataFrame(years, ["Year"])

# Partition by number of years - Spark distributes across available workers
# With 2 workers and 4 partitions: each worker processes 2 years
# With 4 workers and 4 partitions: each worker processes 1 year
num_partitions = len(years)
df_years = df_years.repartition(num_partitions)
print(f"[SPARK] Processing {num_partitions} partitions across available workers")

print("\n[EXTRACTION] Starting Pre-Race feature extraction...")
df_pre_race = df_years.mapInPandas(extract_pre_race_features, schema=schema_pre_race)

pre_race_output = f"gs://{RAW_BUCKET}/processed_features/pre_race_features"
df_pre_race.coalesce(1).write.mode("overwrite").csv(pre_race_output, header=True)
print(f"[EXTRACTION] Pre-Race features saved to {pre_race_output}")

print(f"\n[EXTRACTION] Starting In-Race feature extraction...")
df_in_race = df_years.mapInPandas(extract_in_race_features, schema=schema_in_race)

in_race_output = f"gs://{RAW_BUCKET}/processed_features/in_race_features"
df_in_race.coalesce(1).write.mode("overwrite").csv(in_race_output, header=True)
print(f"[EXTRACTION] In-Race features saved to {in_race_output}")

print("\n[COMPLETE] Feature extraction completed successfully!")
print(f"[COMPLETE] Features available at gs://{RAW_BUCKET}/processed_features/")
