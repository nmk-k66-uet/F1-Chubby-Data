"""
Fast-path Structured Streaming job: Pub/Sub *-viz-fast → InfluxDB.

Reads from three subscriptions (telemetry-viz-fast, timing-viz-fast,
race-control-viz-fast), maps each JSON payload to InfluxDB line protocol,
and writes via the InfluxDB v2 write API in micro-batches (500 ms trigger).

Submit to Dataproc:
    gcloud dataproc jobs submit pyspark spark/streaming_fast.py \
        --cluster $CLUSTER --region $REGION \
        --properties spark.jars.packages=com.google.cloud:pubsub-spark-connector:1.0.0 \
        --pip-packages 'influxdb-client' \
        -- --project $PROJECT_ID --influxdb-url http://$VM_IP:8086 \
           --influxdb-token $TOKEN --race-id 2026_Australian_Grand_Prix
"""

import argparse
import json
import logging
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, udf
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("streaming_fast")

# ── Pub/Sub JSON schemas ────────────────────────────────────────────────────

TIMING_SCHEMA = StructType([
    StructField("timestamp_ms", IntegerType()),
    StructField("driver_id", StringType()),
    StructField("lap_number", IntegerType()),
    StructField("position", IntegerType()),
    StructField("lap_time_ms", DoubleType()),
    StructField("gap_to_leader_ms", DoubleType()),
    StructField("interval_ms", DoubleType()),
    StructField("tyre_compound", StringType()),
    StructField("tyre_age_laps", IntegerType()),
    StructField("stint_number", IntegerType()),
    StructField("pit_in_lap", BooleanType()),
    StructField("pit_out_lap", BooleanType()),
])

TELEMETRY_SCHEMA = StructType([
    StructField("timestamp_ms", IntegerType()),
    StructField("driver_id", StringType()),
    StructField("x", DoubleType()),
    StructField("y", DoubleType()),
    StructField("speed_kph", DoubleType()),
    StructField("throttle_pct", DoubleType()),
    StructField("brake_pct", DoubleType()),
    StructField("gear", IntegerType()),
    StructField("drs", IntegerType()),
    StructField("lap_number", IntegerType()),
    StructField("session_time_sec", DoubleType()),
])

RACE_CONTROL_SCHEMA = StructType([
    StructField("timestamp_ms", IntegerType()),
    StructField("flag", StringType()),
    StructField("scope", StringType()),
    StructField("message", StringType()),
    StructField("driver_id", StringType()),
    StructField("lap_number", IntegerType()),
])

# ── Compound mapping (mirrors simulation script) ────────────────────────────

COMPOUND_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}


# ── InfluxDB batch writer (runs inside foreachBatch) ───────────────────────

def make_influx_writer(url: str, token: str, org: str, bucket: str):
    """Return a foreachBatch callable that writes to InfluxDB."""

    def _write_batch(df, batch_id):
        rows = df.collect()
        if not rows:
            return

        from influxdb_client import InfluxDBClient, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS

        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        try:
            lines = [row["line_protocol"] for row in rows if row["line_protocol"]]
            if lines:
                write_api.write(bucket=bucket, record=lines,
                                write_precision=WritePrecision.MS)
                log.info("batch %s: wrote %d points", batch_id, len(lines))
        finally:
            write_api.close()
            client.close()

    return _write_batch


# ── Line-protocol formatters (UDFs) ────────────────────────────────────────

def _escape_tag(v: str) -> str:
    return v.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def timing_to_line(race_id):
    """Return a UDF that converts a timing row to InfluxDB line protocol."""
    _race_id = _escape_tag(race_id)

    def _fn(driver_id, lap_number, position, lap_time_ms, gap_to_leader_ms,
            interval_ms, tyre_compound, tyre_age_laps, pit_out_lap, timestamp_ms):
        if driver_id is None:
            return None
        driver = _escape_tag(driver_id)
        compound = tyre_compound or "MEDIUM"
        cidx = COMPOUND_IDX.get(compound, 1)
        is_pit_out = 1 if pit_out_lap else 0
        lap_frac = 0.0  # Will be enriched by slow path
        fields = (
            f"position={position or 0}i,"
            f"gap_to_leader={gap_to_leader_ms or 0.0},"
            f"interval={interval_ms or 0.0},"
            f"lap_time_ms={int(lap_time_ms or 0)}i,"
            f'compound="{compound}",'
            f"tyre_life={tyre_age_laps or 0}i,"
            f"compound_idx={cidx}i,"
            f"is_pit_out={is_pit_out}i,"
            f"lap_number={lap_number or 0}i,"
            f"lap_fraction={lap_frac}"
        )
        return f"live_timing,race_id={_race_id},driver={driver} {fields} {timestamp_ms}"

    return udf(_fn, StringType())


def race_control_to_line(race_id):
    """Return a UDF that converts a race-control row to line protocol."""
    _race_id = _escape_tag(race_id)

    def _fn(flag, message, timestamp_ms):
        if message is None:
            return None
        category = "RaceControl"
        _flag = (flag or "").replace('"', '\\"')
        _msg = (message or "").replace('"', '\\"')
        fields = f'message="{_msg}",flag="{_flag}",elapsed_sec=0.0'
        return f"live_race_control,race_id={_race_id},category={_escape_tag(category)} {fields} {timestamp_ms}"

    return udf(_fn, StringType())


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fast streaming: Pub/Sub → InfluxDB")
    p.add_argument("--project", required=True, help="GCP project ID")
    p.add_argument("--influxdb-url", required=True)
    p.add_argument("--influxdb-token", required=True)
    p.add_argument("--influxdb-org", default="f1chubby")
    p.add_argument("--influxdb-bucket", default="live_race")
    p.add_argument("--race-id", required=True, help="e.g. 2026_Australian Grand Prix")
    p.add_argument("--checkpoint-dir", default="/tmp/spark-checkpoints/fast")
    return p.parse_args()


def main():
    args = parse_args()

    spark = (
        SparkSession.builder
        .appName("f1-streaming-fast")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    influx_writer = make_influx_writer(
        args.influxdb_url, args.influxdb_token, args.influxdb_org, args.influxdb_bucket
    )

    # ── 1. Timing stream ────────────────────────────────────────────────────
    timing_raw = (
        spark.readStream
        .format("pubsub")
        .option("subscriptionPath",
                f"projects/{args.project}/subscriptions/f1-timing-viz-fast")
        .load()
    )

    timing_parsed = (
        timing_raw
        .selectExpr("CAST(data AS STRING) AS json_str")
        .select(from_json(col("json_str"), TIMING_SCHEMA).alias("d"))
        .select("d.*")
    )

    timing_line_udf = timing_to_line(args.race_id)
    timing_lines = timing_parsed.select(
        timing_line_udf(
            col("driver_id"), col("lap_number"), col("position"),
            col("lap_time_ms"), col("gap_to_leader_ms"), col("interval_ms"),
            col("tyre_compound"), col("tyre_age_laps"), col("pit_out_lap"),
            col("timestamp_ms"),
        ).alias("line_protocol")
    )

    timing_query = (
        timing_lines.writeStream
        .foreachBatch(influx_writer)
        .option("checkpointLocation", f"{args.checkpoint_dir}/timing")
        .trigger(processingTime="500 milliseconds")
        .start()
    )

    # ── 2. Race-control stream ──────────────────────────────────────────────
    rc_raw = (
        spark.readStream
        .format("pubsub")
        .option("subscriptionPath",
                f"projects/{args.project}/subscriptions/f1-race-control-viz-fast")
        .load()
    )

    rc_parsed = (
        rc_raw
        .selectExpr("CAST(data AS STRING) AS json_str")
        .select(from_json(col("json_str"), RACE_CONTROL_SCHEMA).alias("d"))
        .select("d.*")
    )

    rc_line_udf = race_control_to_line(args.race_id)
    rc_lines = rc_parsed.select(
        rc_line_udf(
            col("flag"), col("message"), col("timestamp_ms"),
        ).alias("line_protocol")
    )

    rc_query = (
        rc_lines.writeStream
        .foreachBatch(influx_writer)
        .option("checkpointLocation", f"{args.checkpoint_dir}/race_control")
        .trigger(processingTime="500 milliseconds")
        .start()
    )

    log.info("Fast streaming started — timing + race-control → InfluxDB")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
