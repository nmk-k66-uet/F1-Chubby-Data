"""
Slow-path streaming job: Pub/Sub pull → Model API → InfluxDB.

Pulls from the f1-timing-pred-slow subscription using the Python Pub/Sub
client, batches messages by driver, calls the Model Serving API for
predictions, and writes the results to InfluxDB (~10 s cycle).

Submit to Dataproc:
    gcloud dataproc jobs submit pyspark spark/streaming_slow.py \
        --cluster $CLUSTER --region $REGION \
        -- --project $PROJECT_ID --influxdb-url http://$VM_IP:8086 \
           --influxdb-token $TOKEN --model-api-url http://$VM_IP:8080
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone

import requests as req
from google.cloud import pubsub_v1

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("streaming_slow")

COMPOUND_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}


def _escape_tag(v: str) -> str:
    return v.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


# ── Prediction logic ──────────────────────────────────────────────────────

def predict(drivers_payload, model_api_url):
    """Call Model API; fall back to heuristic on failure."""
    try:
        resp = req.post(
            f"{model_api_url}/predict-inrace",
            json={"drivers": drivers_payload},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("predictions", [])
    except Exception as e:
        log.warning("Model API failed: %s — using heuristic", e)

    # Heuristic fallback
    predictions = []
    for d in drivers_payload:
        pos = int(d["CurrentPosition"])
        win = max(0.0, 0.75 * (0.55 ** (pos - 1)))
        podium = max(0.0, min(1.0, 0.95 * (0.70 ** (pos - 1))))
        predictions.append({
            "driver": d["driver"],
            "win_prob": round(win, 4),
            "podium_prob": round(podium, 4),
        })
    total_win = sum(p["win_prob"] for p in predictions) or 1.0
    total_pod = sum(p["podium_prob"] for p in predictions) or 1.0
    for p in predictions:
        p["win_prob"] = round(p["win_prob"] / total_win, 4)
        p["podium_prob"] = round(p["podium_prob"] / total_pod * 3.0, 4)
    return predictions


def write_predictions_to_influx(predictions, race_id, driver_laps, url, token, org, bucket):
    """Write prediction line protocol to InfluxDB."""
    if not predictions:
        return
    from influxdb_client import InfluxDBClient, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    _race_id = _escape_tag(race_id)

    lines = []
    for pred in predictions:
        driver = _escape_tag(pred["driver"])
        lap_num = driver_laps.get(pred["driver"], 0)
        fields = (
            f"win_prob={pred['win_prob']},"
            f"podium_prob={pred['podium_prob']},"
            f"lap_number={lap_num}i"
        )
        lines.append(f"predictions,race_id={_race_id},driver={driver} {fields} {now_ms}")

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    try:
        write_api.write(bucket=bucket, record=lines, write_precision=WritePrecision.MS)
        log.info("Wrote %d prediction points to InfluxDB", len(lines))
    finally:
        write_api.close()
        client.close()


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Slow streaming: Pub/Sub pull → Model API → InfluxDB")
    p.add_argument("--project", required=True, help="GCP project ID")
    p.add_argument("--influxdb-url", required=True)
    p.add_argument("--influxdb-token", required=True)
    p.add_argument("--influxdb-org", default="f1chubby")
    p.add_argument("--influxdb-bucket", default="live_race")
    p.add_argument("--model-api-url", required=True, help="e.g. http://10.0.0.2:8080")
    p.add_argument("--duration", type=int, default=1800,
                   help="Max run time in seconds (default: 1800 = 30 min). 0 = unlimited.")
    return p.parse_args()


def main():
    args = parse_args()

    subscriber = pubsub_v1.SubscriberClient()
    timing_sub = subscriber.subscription_path(args.project, "f1-timing-pred-slow")

    deadline = time.monotonic() + args.duration if args.duration > 0 else float("inf")
    log.info("Slow streaming started — pulling %s → Model API → InfluxDB (duration=%ss)", timing_sub, args.duration)

    while time.monotonic() < deadline:
        # Pull a batch of timing messages
        messages = []
        ack_ids = []
        try:
            response = subscriber.pull(
                request={"subscription": timing_sub, "max_messages": 200},
                timeout=10,
            )
            for msg in response.received_messages:
                ack_ids.append(msg.ack_id)
                try:
                    data = json.loads(msg.message.data.decode("utf-8"))
                    messages.append(data)
                except Exception as e:
                    log.warning("Failed to parse message: %s", e)
        except Exception as e:
            if "DEADLINE_EXCEEDED" not in str(e) and "504" not in str(e):
                log.warning("Pull error: %s", e)

        if ack_ids:
            subscriber.acknowledge(request={"subscription": timing_sub, "ack_ids": ack_ids})

        if not messages:
            time.sleep(10)
            continue

        # Deduplicate: keep latest message per driver (highest lap_number)
        latest = {}
        for m in messages:
            driver = m.get("driver_id")
            if not driver:
                continue
            prev = latest.get(driver)
            if prev is None or (m.get("lap_number", 0) or 0) >= (prev.get("lap_number", 0) or 0):
                latest[driver] = m

        if not latest:
            time.sleep(10)
            continue

        # Extract race_id and total_laps from first message
        first = next(iter(latest.values()))
        race_id = first.get("race_id", "unknown")
        total_laps = first.get("total_laps", 1) or 1

        # Build Model API payload
        drivers_payload = []
        driver_laps = {}
        for driver, m in latest.items():
            compound = m.get("tyre_compound") or "MEDIUM"
            cidx = COMPOUND_IDX.get(compound, 1)
            lap_num = m.get("lap_number", 0) or 0
            lap_frac = lap_num / total_laps if total_laps else 0
            drivers_payload.append({
                "driver": driver,
                "LapFraction": lap_frac,
                "CurrentPosition": float(m.get("position", 0) or 0),
                "GapToLeader": float(m.get("gap_to_leader_ms", 0) or 0),
                "TyreLife": float(m.get("tyre_age_laps", 0) or 0),
                "CompoundIdx": float(cidx),
                "IsPitOut": 1.0 if m.get("pit_out_lap") else 0.0,
            })
            driver_laps[driver] = lap_num

        # Predict + write
        predictions = predict(drivers_payload, args.model_api_url)
        try:
            write_predictions_to_influx(
                predictions, race_id, driver_laps,
                args.influxdb_url, args.influxdb_token,
                args.influxdb_org, args.influxdb_bucket,
            )
        except Exception as e:
            log.error("InfluxDB write error: %s", e)

        time.sleep(10)

    log.info("Duration reached (%ss) — exiting.", args.duration)


if __name__ == "__main__":
    main()
