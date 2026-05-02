#!/usr/bin/env python3
"""
Populate GCS cache with F1 session data for 2022-2025.

This script fetches data from FastF1 API and uploads to GCS, so the training
pipeline can run without hitting rate limits.

Usage:
    python scripts/populate_gcs_cache.py <PROJECT_ID>
"""

import os
import sys
import time
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fastf1
from core.gcs_utils import get_schedule, load_with_gcs_cache

# Configuration
if len(sys.argv) > 1:
    PROJECT_ID = sys.argv[1]
else:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    if not PROJECT_ID:
        print("ERROR: Provide PROJECT_ID as argument or set GCP_PROJECT_ID env var")
        sys.exit(1)

RAW_BUCKET = f"f1chubby-raw-{PROJECT_ID}"
CACHE_DIR = "f1_cache_populate"
YEARS = [2022, 2023, 2024, 2025]

# Conservative timing to respect 500 calls/hour limit
# Each race needs ~3 sessions (R, Q, FP2) = 3 API calls
# 22 races/year × 3 sessions = 66 calls/year
# 66 calls ÷ 500 calls/hour = ~8 minutes minimum per year
DELAY_BETWEEN_SESSIONS = 20  # seconds (conservative: 180 calls/hour)

print("=" * 70)
print("F1 GCS Cache Population Script")
print("=" * 70)
print(f"Project ID: {PROJECT_ID}")
print(f"GCS Bucket: gs://{RAW_BUCKET}")
print(f"Cache Dir: {CACHE_DIR}")
print(f"Years: {YEARS}")
print(f"Delay between sessions: {DELAY_BETWEEN_SESSIONS}s")
print("")

# Create cache directory
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level("WARNING")

def load_and_cache(year, round_num, session_type, description):
    """Load session and upload to GCS cache"""
    try:
        print(f"  [{year} R{round_num:02d} {session_type:3s}] Fetching {description}...", end=" ", flush=True)
        start = time.time()

        _ = load_with_gcs_cache(
            year, round_num, session_type,
            telemetry=False, weather=False, messages=False,
            cache_dir=CACHE_DIR,
            project_id=PROJECT_ID,
            gcs_bucket=RAW_BUCKET
        )

        elapsed = time.time() - start
        print(f"✓ ({elapsed:.1f}s)")

        time.sleep(DELAY_BETWEEN_SESSIONS)
        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False

# Main loop
total_sessions = 0
failed_sessions = 0
start_time = time.time()

for year in YEARS:
    print(f"\n{'─' * 70}")
    print(f"YEAR {year}")
    print(f"{'─' * 70}")

    # Get schedule
    schedule = get_schedule(year)
    if schedule.empty:
        print(f"⚠ WARNING: No schedule found for {year}. Skipping.")
        continue

    # Filter completed events
    completed_events = schedule[
        (schedule["EventDate"] < datetime.now())
        & (schedule["RoundNumber"] > 0)
    ]

    print(f"Found {len(completed_events)} completed events")

    year_start = time.time()
    year_sessions = 0
    year_failed = 0

    for _, event in completed_events.iterrows():
        round_num = event["RoundNumber"]
        event_name = event["EventName"]
        event_format = event.get("EventFormat", "conventional").lower()

        print(f"\n[R{round_num:02d}] {event_name}")

        # 1. Load Race (critical)
        if load_and_cache(year, round_num, "R", "Race"):
            year_sessions += 1
            total_sessions += 1
        else:
            year_failed += 1
            failed_sessions += 1
            print(f"  ⚠ Skipping Q and FP2 for R{round_num} due to Race load failure")
            continue

        # 2. Load Qualifying (critical)
        if load_and_cache(year, round_num, "Q", "Qualifying"):
            year_sessions += 1
            total_sessions += 1
        else:
            year_failed += 1
            failed_sessions += 1

        # 3. Load Practice/Sprint (optional)
        pace_session = "S" if event_format in ["sprint", "sprint_qualifying"] else "FP2"
        pace_desc = "Sprint" if pace_session == "S" else "Practice 2"

        if load_and_cache(year, round_num, pace_session, pace_desc):
            year_sessions += 1
            total_sessions += 1
        else:
            year_failed += 1
            failed_sessions += 1
            # Non-critical failure for FP2/Sprint

    year_elapsed = time.time() - year_start
    print(f"\n{year} Summary: {year_sessions} sessions cached, {year_failed} failed ({year_elapsed/60:.1f} minutes)")

# Final summary
total_elapsed = time.time() - start_time
print("\n" + "=" * 70)
print("CACHE POPULATION COMPLETE")
print("=" * 70)
print(f"Total sessions cached: {total_sessions}")
print(f"Failed sessions: {failed_sessions}")
print(f"Total time: {total_elapsed/60:.1f} minutes ({total_elapsed/3600:.2f} hours)")
print(f"GCS Bucket: gs://{RAW_BUCKET}")
print("")

if failed_sessions > 0:
    print(f"⚠ WARNING: {failed_sessions} sessions failed to cache")
    print("Review errors above and consider re-running for failed sessions")
else:
    print("✓ All sessions cached successfully!")
    print("You can now run the training pipeline without API rate limit concerns")
