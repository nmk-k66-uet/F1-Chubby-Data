"""
Fast-path streaming job: Pub/Sub pull → InfluxDB.

Pulls from timing-viz-fast and race-control-viz-fast subscriptions using the
Python Pub/Sub client, converts to InfluxDB line protocol, and writes in
micro-batches (~500 ms).

Submit to Dataproc:
    gcloud dataproc jobs submit pyspark spark/streaming_fast.py \
        --cluster $CLUSTER --region $REGION \
        -- --project $PROJECT_ID --influxdb-url http://$VM_IP:8086 \
           --influxdb-token $TOKEN
"""

import argparse
import json
import logging
import time

from google.cloud import pubsub_v1

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("streaming_fast")

COMPOUND_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}


# ── Line-protocol helpers ──────────────────────────────────────────────────

def _escape_tag(v: str) -> str:
    return v.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def timing_to_line(msg):
    """Convert a timing message dict to InfluxDB line protocol string."""
    driver_id = msg.get("driver_id")
    race_id = msg.get("race_id")
    if not driver_id or not race_id:
        return None

    _race_id = _escape_tag(race_id)
    driver = _escape_tag(driver_id)
    compound = msg.get("tyre_compound") or "MEDIUM"
    cidx = COMPOUND_IDX.get(compound, 1)
    is_pit_out = 1 if msg.get("pit_out_lap") else 0
    timestamp_ms = msg.get("timestamp_ms", 0)

    fields = (
        f"position={msg.get('position', 0) or 0}i,"
        f"gap_to_leader={msg.get('gap_to_leader_ms', 0.0) or 0.0},"
        f"interval={msg.get('interval_ms', 0.0) or 0.0},"
        f"lap_time_ms={int(msg.get('lap_time_ms', 0) or 0)}i,"
        f'compound="{compound}",'
        f"tyre_life={msg.get('tyre_age_laps', 0) or 0}i,"
        f"compound_idx={cidx}i,"
        f"is_pit_out={is_pit_out}i,"
        f"lap_number={msg.get('lap_number', 0) or 0}i,"
        f"lap_fraction=0.0"
    )
    return f"live_timing,race_id={_race_id},driver={driver} {fields} {timestamp_ms}"


def race_control_to_line(msg):
    """Convert a race-control message dict to InfluxDB line protocol string."""
    message = msg.get("message")
    race_id = msg.get("race_id")
    if not message or not race_id:
        return None

    _race_id = _escape_tag(race_id)
    _flag = (msg.get("flag") or "").replace('"', '\\"')
    _msg = message.replace('"', '\\"')
    timestamp_ms = msg.get("timestamp_ms", 0)

    fields = f'message="{_msg}",flag="{_flag}",elapsed_sec=0.0'
    return f"live_race_control,race_id={_race_id},category=RaceControl {fields} {timestamp_ms}"


# ── InfluxDB writer ────────────────────────────────────────────────────────

def write_to_influx(lines, url, token, org, bucket):
    """Write line protocol strings to InfluxDB."""
    if not lines:
        return
    from influxdb_client import InfluxDBClient, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    try:
        write_api.write(bucket=bucket, record=lines, write_precision=WritePrecision.MS)
        log.info("Wrote %d points to InfluxDB", len(lines))
    finally:
        write_api.close()
        client.close()


# ── Pull helpers ───────────────────────────────────────────────────────────

def pull_and_convert(subscriber, subscription, converter, max_messages=100):
    """Pull messages, convert each with `converter`, return (lines, ack_ids)."""
    lines = []
    ack_ids = []
    try:
        response = subscriber.pull(
            request={"subscription": subscription, "max_messages": max_messages},
            timeout=5,
        )
        for msg in response.received_messages:
            ack_ids.append(msg.ack_id)
            try:
                data = json.loads(msg.message.data.decode("utf-8"))
                line = converter(data)
                if line:
                    lines.append(line)
            except Exception as e:
                log.warning("Failed to parse message: %s", e)
    except Exception as e:
        if "DEADLINE_EXCEEDED" not in str(e) and "504" not in str(e):
            log.warning("Pull error on %s: %s", subscription, e)
    return lines, ack_ids


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fast streaming: Pub/Sub pull → InfluxDB")
    p.add_argument("--project", required=True, help="GCP project ID")
    p.add_argument("--influxdb-url", required=True)
    p.add_argument("--influxdb-token", required=True)
    p.add_argument("--influxdb-org", default="f1chubby")
    p.add_argument("--influxdb-bucket", default="live_race")
    p.add_argument("--duration", type=int, default=1800,
                   help="Max run time in seconds (default: 1800 = 30 min). 0 = unlimited.")
    return p.parse_args()


def main():
    args = parse_args()

    subscriber = pubsub_v1.SubscriberClient()
    timing_sub = subscriber.subscription_path(args.project, "f1-timing-viz-fast")
    rc_sub = subscriber.subscription_path(args.project, "f1-race-control-viz-fast")

    deadline = time.monotonic() + args.duration if args.duration > 0 else float("inf")
    log.info("Fast streaming started — pulling timing + race-control → InfluxDB (duration=%ss)", args.duration)

    while time.monotonic() < deadline:
        lines = []

        # Pull timing messages
        t_lines, t_acks = pull_and_convert(subscriber, timing_sub, timing_to_line)
        lines.extend(t_lines)
        if t_acks:
            subscriber.acknowledge(request={"subscription": timing_sub, "ack_ids": t_acks})

        # Pull race-control messages
        rc_lines, rc_acks = pull_and_convert(subscriber, rc_sub, race_control_to_line, max_messages=50)
        lines.extend(rc_lines)
        if rc_acks:
            subscriber.acknowledge(request={"subscription": rc_sub, "ack_ids": rc_acks})

        # Write batch to InfluxDB
        if lines:
            try:
                write_to_influx(
                    lines, args.influxdb_url, args.influxdb_token,
                    args.influxdb_org, args.influxdb_bucket,
                )
            except Exception as e:
                log.error("InfluxDB write error: %s", e)

        time.sleep(0.5)

    log.info("Duration reached (%ss) — exiting.", args.duration)


if __name__ == "__main__":
    main()
