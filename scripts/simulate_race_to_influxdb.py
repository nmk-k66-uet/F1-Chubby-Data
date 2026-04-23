#!/usr/bin/env python3
"""
Simulate Race → InfluxDB

Extracts lap-by-lap data from a cached FastF1 race session and drip-feeds it
into InfluxDB measurements (`live_timing`, `predictions`, `live_race_control`).

Usage:
    # Drip-feed at 1 lap/sec (default)
    python scripts/simulate_race_to_influxdb.py

    # Faster replay: 5 laps/sec
    python scripts/simulate_race_to_influxdb.py --speed 5

    # Tear down all simulation data
    python scripts/simulate_race_to_influxdb.py --teardown

Environment variables (or defaults for local docker compose):
    INFLUXDB_URL    http://localhost:8086
    INFLUXDB_TOKEN  f1chubby-influx-token
    INFLUXDB_ORG    f1chubby
    INFLUXDB_BUCKET live_race
    MODEL_API_URL   http://localhost:8080
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import fastf1
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# InfluxDB connection defaults (match docker-compose.yml)
# ---------------------------------------------------------------------------
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "f1chubby-influx-token")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "f1chubby")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "live_race")
MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://localhost:8080")

# Race to simulate
YEAR = 2026
ROUND_NUM = 1  # Australian GP is round 2 in 2026
EVENT_NAME = "Australian Grand Prix"
RACE_ID = f"{YEAR}_{EVENT_NAME}"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "f1_cache")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_influx_client():
    from influxdb_client import InfluxDBClient
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


def teardown(client):
    """Delete all simulation data from InfluxDB."""
    delete_api = client.delete_api()
    start = "1970-01-01T00:00:00Z"
    stop = "2099-12-31T23:59:59Z"

    for measurement in ("live_timing", "predictions", "live_race_control"):
        print(f"  Deleting measurement={measurement} for race_id={RACE_ID} ...")
        delete_api.delete(
            start, stop,
            predicate=f'_measurement="{measurement}" AND race_id="{RACE_ID}"',
            bucket=INFLUXDB_BUCKET,
            org=INFLUXDB_ORG,
        )
    print("Teardown complete.")


def load_session():
    """Load the 2026 Australian GP Race session from local FastF1 cache."""
    cache_dir = os.path.abspath(CACHE_DIR)
    fastf1.Cache.enable_cache(cache_dir)
    fastf1.set_log_level("WARNING")

    print(f"Loading {YEAR} {EVENT_NAME} Race session from cache …")
    session = fastf1.get_session(YEAR, ROUND_NUM, "R")
    session.load(telemetry=False, weather=False, messages=True)
    return session


def prepare_lap_data(session):
    """
    Extract and enrich lap-by-lap data from the session.
    Returns (laps_df, total_laps, race_control_msgs).
    """
    laps = session.laps.copy()
    if laps.empty:
        print("ERROR: No lap data in session.", file=sys.stderr)
        sys.exit(1)

    total_laps = int(laps["LapNumber"].max())

    # Feature engineering (mirrors prepare_stream_data in tab_live_race.py)
    laps["CompoundIdx"] = laps["Compound"].map(
        {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}
    ).fillna(1).astype(int)
    laps["IsPitOut"] = laps["PitOutTime"].notna().astype(int)
    laps["LapFraction"] = laps["LapNumber"] / total_laps

    # Gap to leader
    leader_times = laps[laps["Position"] == 1].set_index("LapNumber")["Time"]

    def calc_gap(row):
        ln = row["LapNumber"]
        if ln in leader_times.index and pd.notna(row["Time"]):
            gap = (row["Time"] - leader_times[ln]).total_seconds()
            return max(0.0, gap)
        return 0.0

    laps["GapToLeader"] = laps.apply(calc_gap, axis=1)
    laps.rename(columns={"Position": "CurrentPosition"}, inplace=True)

    # Interval to car ahead
    laps = laps.sort_values(["LapNumber", "CurrentPosition"])
    laps["Interval"] = laps.groupby("LapNumber")["GapToLeader"].diff()
    laps.loc[laps["CurrentPosition"] == 1, "Interval"] = 0.0
    laps["Interval"] = laps["Interval"].fillna(0.0).apply(lambda x: max(0.0, x))

    # Lap time in milliseconds
    laps["LapTimeMs"] = laps["LapTime"].apply(
        lambda td: int(td.total_seconds() * 1000) if pd.notna(td) else 0
    )

    # Race control messages
    rc_msgs = []
    if hasattr(session, "race_control_messages") and session.race_control_messages is not None:
        rcm = session.race_control_messages
        for _, row in rcm.iterrows():
            rc_msgs.append({
                "time": row.get("Time", pd.NaT),
                "category": str(row.get("Category", "Other")),
                "message": str(row.get("Message", "")),
                "flag": str(row.get("Flag", "")),
            })

    return laps, total_laps, rc_msgs


def predict_for_lap(lap_df, total_laps):
    """
    Get predictions for a lap. Tries Model Serving API first, falls back to
    position-based heuristic.
    Returns list of dicts: [{driver, win_prob, podium_prob}, ...]
    """
    # Try Model Serving API
    try:
        drivers_payload = []
        for _, row in lap_df.iterrows():
            drivers_payload.append({
                "driver": str(row["Driver"]),
                "LapFraction": float(row.get("LapFraction", 0)),
                "CurrentPosition": float(row["CurrentPosition"]),
                "GapToLeader": float(row.get("GapToLeader", 0)),
                "TyreLife": float(row.get("TyreLife", 0)),
                "CompoundIdx": float(row.get("CompoundIdx", 1)),
                "IsPitOut": float(row.get("IsPitOut", 0)),
            })

        resp = requests.post(
            f"{MODEL_API_URL}/predict-inrace",
            json={"drivers": drivers_payload},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()["predictions"]
    except Exception:
        pass

    # Heuristic fallback: higher position → higher probability
    results = []
    for _, row in lap_df.iterrows():
        pos = int(row["CurrentPosition"])
        # Exponential decay based on position
        win = max(0.0, 0.75 * (0.55 ** (pos - 1)))
        podium = max(0.0, min(1.0, 0.95 * (0.70 ** (pos - 1))))
        results.append({
            "driver": str(row["Driver"]),
            "win_prob": round(win, 4),
            "podium_prob": round(podium, 4),
        })

    # Normalize win probs to sum to 1.0
    total_win = sum(r["win_prob"] for r in results) or 1.0
    for r in results:
        r["win_prob"] = round(r["win_prob"] / total_win, 4)

    # Normalize podium probs to sum to 3.0
    total_pod = sum(r["podium_prob"] for r in results) or 1.0
    for r in results:
        r["podium_prob"] = round(r["podium_prob"] / total_pod * 3.0, 4)

    return results


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_timing_for_lap(write_api, lap_df, lap_number, timestamp):
    """Write live_timing points for one lap (all drivers)."""
    from influxdb_client import Point

    for _, row in lap_df.iterrows():
        p = (
            Point("live_timing")
            .tag("race_id", RACE_ID)
            .tag("driver", str(row["Driver"]))
            .field("position", int(row["CurrentPosition"]))
            .field("gap_to_leader", float(row.get("GapToLeader", 0)))
            .field("interval", float(row.get("Interval", 0)))
            .field("lap_time_ms", int(row.get("LapTimeMs", 0)))
            .field("compound", str(row.get("Compound", "MEDIUM")))
            .field("tyre_life", int(row.get("TyreLife", 0)))
            .field("compound_idx", int(row.get("CompoundIdx", 1)))
            .field("is_pit_out", int(row.get("IsPitOut", 0)))
            .field("lap_number", int(lap_number))
            .field("lap_fraction", float(row.get("LapFraction", 0)))
            .time(timestamp)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, record=p)


def write_predictions_for_lap(write_api, predictions, lap_number, timestamp):
    """Write predictions points for one lap (all drivers)."""
    from influxdb_client import Point

    for pred in predictions:
        p = (
            Point("predictions")
            .tag("race_id", RACE_ID)
            .tag("driver", pred["driver"])
            .field("win_prob", float(pred["win_prob"]))
            .field("podium_prob", float(pred["podium_prob"]))
            .field("lap_number", int(lap_number))
            .time(timestamp)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, record=p)


def write_race_control(write_api, rc_msgs, race_start_time, base_ts):
    """Write all race control messages at once, mapped to wall-clock timestamps."""
    from influxdb_client import Point

    if not rc_msgs:
        return

    for msg in rc_msgs:
        # Map race elapsed time to simulation timestamp
        if pd.notna(msg["time"]):
            try:
                t = pd.Timedelta(msg["time"]) if not isinstance(msg["time"], pd.Timedelta) else msg["time"]
                elapsed = max(0.0, t / pd.Timedelta(seconds=1))
            except Exception:
                elapsed = 0.0
        else:
            elapsed = 0.0
        ts = base_ts  # Write all at start; they'll be filtered by race_id

        p = (
            Point("live_race_control")
            .tag("race_id", RACE_ID)
            .tag("category", msg["category"])
            .field("message", msg["message"])
            .field("flag", msg["flag"])
            .field("elapsed_sec", float(elapsed))
            .time(ts)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, record=p)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulate F1 race → InfluxDB")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Replay speed in laps per second (default: 1.0)")
    parser.add_argument("--teardown", action="store_true",
                        help="Delete all simulation data from InfluxDB and exit")
    args = parser.parse_args()

    client = get_influx_client()

    if args.teardown:
        print(f"Tearing down data for race_id={RACE_ID} …")
        teardown(client)
        client.close()
        return

    # --- Load and prepare data ---
    session = load_session()
    laps_df, total_laps, rc_msgs = prepare_lap_data(session)

    print(f"Race: {YEAR} {EVENT_NAME}")
    print(f"Total laps: {total_laps}")
    print(f"Drivers: {laps_df['Driver'].nunique()}")
    print(f"Race control messages: {len(rc_msgs)}")
    print(f"Replay speed: {args.speed} laps/sec")
    print()

    # --- Teardown existing data before fresh simulation ---
    print("Clearing previous simulation data …")
    teardown(client)

    from influxdb_client.client.write_api import SYNCHRONOUS
    write_api = client.write_api(write_options=SYNCHRONOUS)

    # --- Write race control messages upfront ---
    race_start_time = session.laps["Time"].min() if not session.laps.empty else None
    base_ts = datetime.now(timezone.utc)
    write_race_control(write_api, rc_msgs, race_start_time, base_ts)
    if rc_msgs:
        print(f"Wrote {len(rc_msgs)} race control messages.")

    # --- Drip-feed lap by lap ---
    delay = 1.0 / args.speed if args.speed > 0 else 1.0

    for lap_num in range(1, total_laps + 1):
        ts = datetime.now(timezone.utc)

        lap_data = laps_df[laps_df["LapNumber"] == lap_num].dropna(subset=["CurrentPosition"]).copy()
        lap_data = lap_data.sort_values("CurrentPosition")

        if lap_data.empty:
            print(f"  Lap {lap_num:>2}/{total_laps}  — no data, skipping")
            continue

        # Fast path: live_timing
        write_timing_for_lap(write_api, lap_data, lap_num, ts)

        # Slow path: predictions (written ~1s later to simulate slow path delay)
        predictions = predict_for_lap(lap_data, total_laps)
        pred_ts = datetime.now(timezone.utc)
        write_predictions_for_lap(write_api, predictions, lap_num, pred_ts)

        leader = lap_data.iloc[0]["Driver"]
        print(f"  Lap {lap_num:>2}/{total_laps}  | Leader: {leader}  | {len(lap_data)} drivers  | ✓ timing + predictions")

        if lap_num < total_laps:
            time.sleep(delay)

    print()
    print(f"Simulation complete — {total_laps} laps written to InfluxDB.")
    print(f"  Bucket:  {INFLUXDB_BUCKET}")
    print(f"  Race ID: {RACE_ID}")

    write_api.close()
    client.close()


if __name__ == "__main__":
    main()
