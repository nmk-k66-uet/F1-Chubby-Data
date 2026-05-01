import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    IntegerType,
    FloatType,
    StringType,
)
import os
import sys

is_local = sys.platform == "win32"

if is_local:
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    os.environ["SPARK_LOCAL_IP"] = "localhost"
    os.environ["JDK_JAVA_OPTIONS"] = (
        "--add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED"
    )
    os.environ["HADOOP_HOME"] = "D:\\hadoop"
    os.environ["PATH"] += os.pathsep + "D:\\hadoop\\bin"

if len(sys.argv) > 1:
    PROJECT_ID = sys.argv[1]
else:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "default-project-id")
RAW_BUCKET = f"f1chubby-raw-{PROJECT_ID}"
MODELS_BUCKET = f"f1chubby-model-{PROJECT_ID}"

builder = SparkSession.builder.appName("F1_Model_Training_Pipeline")

if is_local:
    # Local Windows Testing Configurations
    builder = (
        builder.master("local[*]")
        .config("spark.driver.host", "localhost")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config(
            "spark.jars.packages",
            "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.22",
        )
        .config(
            "spark.hadoop.fs.gs.impl",
            "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem",
        )
        .config(
            "spark.hadoop.fs.AbstractFileSystem.gs.impl",
            "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFS",
        )
        .config("spark.hadoop.google.cloud.auth.service.account.enable", "true")
        .config("spark.python.worker.faulthandler.enabled", "true")
        .config("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true")
    )

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
    from core.ml_core import (
        extract_best_q_time,
        extract_fp2_long_run_pace,
        get_team_tier,
    )

    import uuid

    unique_cache_dir = f"f1_cache_{uuid.uuid4().hex}"
    os.makedirs(unique_cache_dir, exist_ok=True)

    def load(
        year, round_num, session_type, telemetry=False, weather=False, messages=False
    ):
        return load_with_gcs_cache(
            year,
            round_num,
            session_type,
            telemetry,
            weather,
            messages,
            cache_dir=unique_cache_dir,
            project_id=PROJECT_ID,
            gcs_bucket=RAW_BUCKET,
        )

    fastf1.Cache.enable_cache(unique_cache_dir)
    fastf1.set_log_level("ERROR")

    for pdf in iterator:
        batch_features = []

        for _, row in pdf.iterrows():
            year = int(row["Year"])

            # Use get_schedule from data_loader
            try:
                schedule = get_schedule(year)
                if schedule.empty:
                    continue
                completed_events = schedule[
                    (schedule["EventDate"] < datetime.now())
                    & (schedule["RoundNumber"] > 0)
                ]
            except Exception as e:
                print(f"Error fetching schedule for {year}: {e}")
                continue

            driver_points = {}

            for _, event in completed_events.iterrows():
                round_num = event["RoundNumber"]

                # 1. Tải Race Result để tính điểm Form (DriverForm)
                try:
                    race = load(
                        year,
                        round_num,
                        "R",
                        telemetry=False,
                        weather=False,
                        messages=False,
                    )
                    r_results = race.results

                    form_dict = {}
                    max_pts = max(1, (round_num - 1) * 26)
                    for drv in r_results["Abbreviation"]:
                        form_dict[drv] = driver_points.get(drv, 0) / max_pts

                    for _, r_row in r_results.iterrows():
                        drv = r_row["Abbreviation"]
                        driver_points[drv] = driver_points.get(drv, 0) + pd.to_numeric(
                            r_row["Points"], errors="coerce"
                        )
                except Exception as e:
                    print(f"    [!] Lỗi đọc Race chặng {round_num} năm {year}: {e}")
                    continue

                # 2. Lấy Qualifying
                try:
                    qualy = load(
                        year,
                        round_num,
                        "Q",
                        telemetry=False,
                        weather=False,
                        messages=False,
                    )
                    q_results = qualy.results
                    pole_time = None
                    if not q_results.empty:
                        all_q_times = q_results.apply(
                            extract_best_q_time, axis=1
                        ).dropna()
                        if not all_q_times.empty:
                            pole_time = all_q_times.min()
                except Exception as e:
                    q_results = pd.DataFrame()
                    pole_time = None

                # 3. Lấy Long Run Pace (FP2 or Sprint)
                format_type = event.get("EventFormat", "conventional").lower()
                pace_session_code = (
                    "S" if format_type in ["sprint", "sprint_qualifying"] else "FP2"
                )
                fp2_deltas = {}
                try:
                    pace_session = load(
                        year,
                        round_num,
                        pace_session_code,
                        telemetry=False,
                        weather=False,
                        messages=False,
                    )
                    fp2_deltas = extract_fp2_long_run_pace(pace_session)
                except:
                    pass

                # 4. Xây dựng Features
                for _, r_row in r_results.iterrows():
                    driver = r_row["Abbreviation"]
                    grid_pos = pd.to_numeric(r_row["GridPosition"], errors="coerce")
                    if pd.isna(grid_pos) or grid_pos == 0:
                        grid_pos = 20

                    tier = get_team_tier(r_row["TeamName"])

                    q_delta = 2.5
                    if (
                        not q_results.empty
                        and driver in q_results["Abbreviation"].values
                    ):
                        driver_q = q_results[q_results["Abbreviation"] == driver].iloc[
                            0
                        ]
                        best_q = extract_best_q_time(driver_q)
                        if best_q is not None and pole_time is not None:
                            q_delta = best_q - pole_time

                    fp2_delta = fp2_deltas.get(driver, np.nan)
                    form = form_dict.get(driver, 0.0)

                    # Lưu vị trí thực tế
                    pos = pd.to_numeric(r_row["Position"], errors="coerce")
                    is_podium = 1 if pd.notna(pos) and pos <= 3 else 0

                    batch_features.append(
                        {
                            "Year": year,
                            "Round": round_num,
                            "Driver": driver,
                            "GridPosition": int(grid_pos),
                            "TeamTier": tier,
                            "QualifyingDelta": float(max(0, q_delta)),
                            "FP2_PaceDelta": (
                                float(fp2_delta) if pd.notna(fp2_delta) else 2.0
                            ),  # default 2.0 if missing
                            "DriverForm": float(form),
                            "Podium": is_podium,
                        }
                    )

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

    unique_cache_dir = f"f1_cache_{uuid.uuid4().hex}"
    os.makedirs(unique_cache_dir, exist_ok=True)

    def load(
        year, round_num, session_type, telemetry=False, weather=False, messages=False
    ):
        return load_with_gcs_cache(
            year,
            round_num,
            session_type,
            telemetry,
            weather,
            messages,
            cache_dir=unique_cache_dir,
        )

    fastf1.Cache.enable_cache(unique_cache_dir)
    fastf1.set_log_level("ERROR")

    for pdf in iterator:
        batch_features = []
        for _, row in pdf.iterrows():
            year = int(row["Year"])

            try:
                schedule = get_schedule(year)
                if schedule.empty:
                    continue
                completed_events = schedule[
                    (schedule["EventDate"] < datetime.now())
                    & (schedule["RoundNumber"] > 0)
                ]
            except:
                continue

            for _, event in completed_events.iterrows():
                round_num = event["RoundNumber"]

                try:
                    race = load(
                        year,
                        round_num,
                        "R",
                        telemetry=False,
                        weather=False,
                        messages=False,
                    )
                    laps = race.laps
                    results = race.results
                except Exception as e:
                    print(f"Error loading race {year} round {round_num}: {e}")
                    continue

                if laps.empty or results.empty:
                    continue

                final_positions = {}
                for _, r_row in results.iterrows():
                    drv = r_row["Abbreviation"]
                    pos = pd.to_numeric(r_row["Position"], errors="coerce")
                    final_positions[drv] = int(pos) if pd.notna(pos) else 20

                total_laps = laps["LapNumber"].max()

                for lap_num, lap_group in laps.groupby("LapNumber"):
                    valid_times = lap_group.dropna(subset=["Time"])
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
    StructField("Podium", IntegerType(), True)
])

# Create the work queue DataFrame
df_years = spark.createDataFrame(years, ["Year"])

# Repartition to distribute each year to a different worker
df_years = df_years.repartition(4)

# Run the distributed extraction
df_pre_race_features = df_years.mapInPandas(extract_pre_race_features, schema=schema_pre_race)

# Save these distributed features to a single file in GCS by coalescing to 1 partition
df_pre_race_features.coalesce(1).write.mode("overwrite").csv(f"gs://{RAW_BUCKET}/processed_features/pre_race_features", header=True)

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
df_in_race_features.coalesce(1).write.mode("overwrite").csv(f"gs://{RAW_BUCKET}/processed_features/in_race_features", header=True)

# ==========================================
# 4. Model Training & Upload
# ==========================================
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn.metrics import accuracy_score, classification_report
import joblib
from google.cloud import storage

def generate_report(model, X_test, y_test, model_name, file_path):
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"=== MÔ HÌNH DỰ ĐOÁN {model_name} - BÁO CÁO HIỆU SUẤT ===\n")
        f.write(f"Thời gian huấn luyện: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Bộ siêu tham số tốt nhất (Best Params): {model.best_params_}\n")
        f.write(f"Độ chính xác tổng thể (Accuracy): {acc:.4f}\n")
        f.write("-" * 60 + "\n")
        f.write("Classification Report:\n")
        f.write(report)

print("\n[ML] Starting Model Training Phase...")

# 1. Read features from GCS into Pandas
print("[ML] Reading Pre-Race features...")
pre_race_df = spark.read.csv(f"gs://{RAW_BUCKET}/processed_features/pre_race_features", header=True, inferSchema=True).toPandas()

# Pre-Race Training
# Handle missing FP2 pace
pre_race_df['FP2_PaceDelta'] = pre_race_df['FP2_PaceDelta'].fillna(pre_race_df.groupby('TeamTier')['FP2_PaceDelta'].transform('median'))
pre_race_df['FP2_PaceDelta'] = pre_race_df['FP2_PaceDelta'].fillna(2.0)

X_pre = pre_race_df[['GridPosition', 'TeamTier', 'QualifyingDelta', 'FP2_PaceDelta', 'DriverForm']]
if 'Podium' in pre_race_df.columns:
    y_pre = pre_race_df['Podium']
else:
    y_pre = (pre_race_df['FinalPosition'] <= 3).astype(int)

X_train_pre, X_test_pre, y_train_pre, y_test_pre = train_test_split(X_pre, y_pre, test_size=0.2, random_state=42, stratify=y_pre)

print("[ML] Tuning Pre-Race Model...")
base_pre = RandomForestClassifier(random_state=42, class_weight='balanced')
grid_pre = GridSearchCV(base_pre, 
                        param_grid={
                            'n_estimators': [50, 100, 150, 200],
                            'max_depth': [4, 6, 8, 10], 
                            'min_samples_split': [2, 5, 10], 
                            'min_samples_leaf': [1, 2, 4], 
                            'bootstrap': [True, False]}, 
                        cv=5, 
                        scoring='f1', 
                        n_jobs=-1, 
                        verbose=1)
grid_pre.fit(X_train_pre, y_train_pre)


generate_report(grid_pre, X_test_pre, y_test_pre, "F1 PRE-RACE PODIUM", 'pre_race_metrics.txt')
joblib.dump(grid_pre.best_estimator_, 'pre_race_model.pkl')


#In-Race Training
print("[ML] Reading In-Race features...")
in_race_df = spark.read.csv(f"gs://{RAW_BUCKET}/processed_features/in_race_features", header=True, inferSchema=True).toPandas()
in_race_df = in_race_df.dropna(subset=['CurrentPosition', 'GapToLeader', 'TyreLife'])

X_in = in_race_df[['LapFraction', 'CurrentPosition', 'GapToLeader', 'TyreLife', 'CompoundIdx', 'IsPitOut']]
y_win = (in_race_df['FinalPosition'] == 1).astype(int)
y_pod = (in_race_df['FinalPosition'] <= 3).astype(int)

X_train_in, X_test_in, y_train_win, y_test_win, y_train_pod, y_test_pod = train_test_split(X_in, y_win, y_pod, test_size=0.2, random_state=42, stratify=y_pod)

print("[ML] Tuning In-Race Win Model...")
base_win = RandomForestClassifier(random_state=42, class_weight='balanced')
search_win = RandomizedSearchCV(base_win, param_distributions={'n_estimators': [100], 'max_depth': [8, 12]}, n_iter=2, cv=3, scoring='f1', n_jobs=-1, random_state=42)
search_win.fit(X_train_in, y_train_win)
joblib.dump(search_win.best_estimator_, 'in_race_win_model.pkl')
generate_report(search_win, X_test_in, y_test_win, "F1 IN-RACE WIN", 'in_race_win_metrics.txt')

print("[ML] Tuning In-Race Podium Model...")
base_pod = RandomForestClassifier(random_state=42, class_weight='balanced')
search_pod = RandomizedSearchCV(base_pod, param_distributions={'n_estimators': [100], 'max_depth': [8, 12]}, n_iter=2, cv=3, scoring='f1', n_jobs=-1, random_state=42)
search_pod.fit(X_train_in, y_train_pod)
joblib.dump(search_pod.best_estimator_, 'in_race_podium_model.pkl')
generate_report(search_pod, X_test_in, y_test_pod, "F1 IN-RACE PODIUM", 'in_race_podium_metrics.txt')

# Upload to GCS
print(f"[ML] Uploading models to gs://{MODELS_BUCKET}/ ...")
def upload_model(file_name):
    try:
        client = storage.Client()
        bucket = client.bucket(MODELS_BUCKET)
        if not bucket.exists():
            bucket = client.create_bucket(MODELS_BUCKET, location="asia-southeast1")
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_name)
        print(f"Uploaded {file_name}")
    except Exception as e:
        print(f"Failed to upload {file_name}: {e}")

upload_model('pre_race_model.pkl')
upload_model('pre_race_metrics.txt')
upload_model('in_race_win_model.pkl')
upload_model('in_race_win_metrics.txt')
upload_model('in_race_podium_model.pkl')
upload_model('in_race_podium_metrics.txt')
print("[ML] Training Pipeline Completed Successfully!")
