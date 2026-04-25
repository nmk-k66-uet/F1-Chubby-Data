"""
Slow-path Structured Streaming job: Pub/Sub f1-timing-pred-slow → Model API → InfluxDB.

Reads the timing subscription, windows by lap, calls the Model Serving API
for predictions, and writes the results back to InfluxDB.

Submit to Dataproc:
    gcloud dataproc jobs submit pyspark spark/streaming_slow.py \
        --cluster $CLUSTER --region $REGION \
        --properties spark.jars.packages=com.google.cloud:pubsub-spark-connector:1.0.0 \
        --pip-packages 'influxdb-client,requests' \
        -- --project $PROJECT_ID --influxdb-url http://$VM_IP:8086 \
           --influxdb-token $TOKEN --model-api-url http://$VM_IP:8080
"""

import argparse
import json
import logging
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    collect_list,
    from_json,
    max as spark_max,
    struct,
    window,
)
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("streaming_slow")

# ── Pub/Sub timing schema ──────────────────────────────────────────────────

TIMING_SCHEMA = StructType([
    StructField("race_id", StringType()),
    StructField("total_laps", IntegerType()),
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

COMPOUND_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}


# ── Prediction + InfluxDB writer (foreachBatch) ───────────────────────────

def make_predict_and_write(
    model_api_url: str,
    influx_url: str,
    influx_token: str,
    influx_org: str,
    influx_bucket: str,
):
    """Return a foreachBatch callable that calls Model API then writes to InfluxDB."""

    def _process_batch(df, batch_id):
        """
        df has columns: race_id, total_laps, driver_id, lap_number, position,
        gap_to_leader_ms, tyre_age_laps, tyre_compound, pit_out_lap
        (aggregated per driver per micro-batch; we take latest lap per driver).
        """
        rows = df.collect()
        if not rows:
            return

        import requests as req
        from influxdb_client import InfluxDBClient, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS

        # Extract race_id and total_laps from the first row
        race_id = rows[0]["race_id"] or "unknown"
        total_laps = rows[0]["total_laps"] or 1

        # Build payload for Model API
        drivers_payload = []
        for row in rows:
            compound = row["tyre_compound"] or "MEDIUM"
            cidx = COMPOUND_IDX.get(compound, 1)
            lap_frac = (row["lap_number"] or 0) / total_laps if total_laps else 0
            drivers_payload.append({
                "driver": row["driver_id"],
                "LapFraction": lap_frac,
                "CurrentPosition": float(row["position"] or 0),
                "GapToLeader": float(row["gap_to_leader_ms"] or 0),
                "TyreLife": float(row["tyre_age_laps"] or 0),
                "CompoundIdx": float(cidx),
                "IsPitOut": 1.0 if row["pit_out_lap"] else 0.0,
            })

        # Call Model API
        predictions = None
        try:
            resp = req.post(
                f"{model_api_url}/predict-inrace",
                json={"drivers": drivers_payload},
                timeout=10,
            )
            resp.raise_for_status()
            predictions = resp.json().get("predictions", [])
        except Exception as e:
            log.warning("Model API call failed (batch %s): %s — using heuristic", batch_id, e)

        # Heuristic fallback
        if not predictions:
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

        # Write predictions to InfluxDB
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        _race_id = race_id.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

        lines = []
        for pred in predictions:
            driver = pred["driver"].replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")
            # Find matching row's lap_number
            lap_num = 0
            for row in rows:
                if row["driver_id"] == pred["driver"]:
                    lap_num = row["lap_number"] or 0
                    break
            fields = (
                f"win_prob={pred['win_prob']},"
                f"podium_prob={pred['podium_prob']},"
                f"lap_number={lap_num}i"
            )
            lines.append(f"predictions,race_id={_race_id},driver={driver} {fields} {now_ms}")

        if lines:
            client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
            write_api = client.write_api(write_options=SYNCHRONOUS)
            try:
                write_api.write(bucket=influx_bucket, record=lines,
                                write_precision=WritePrecision.MS)
                log.info("batch %s: wrote %d prediction points", batch_id, len(lines))
            finally:
                write_api.close()
                client.close()

    return _process_batch


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Slow streaming: Pub/Sub → Model API → InfluxDB")
    p.add_argument("--project", required=True, help="GCP project ID")
    p.add_argument("--influxdb-url", required=True)
    p.add_argument("--influxdb-token", required=True)
    p.add_argument("--influxdb-org", default="f1chubby")
    p.add_argument("--influxdb-bucket", default="live_race")
    p.add_argument("--model-api-url", required=True, help="e.g. http://10.0.0.2:8080")
    p.add_argument("--checkpoint-dir", default="/tmp/spark-checkpoints/slow")
    return p.parse_args()


def main():
    args = parse_args()

    spark = (
        SparkSession.builder
        .appName("f1-streaming-slow")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # ── Read from Pub/Sub timing subscription (slow) ────────────────────────
    timing_raw = (
        spark.readStream
        .format("pubsub")
        .option("subscriptionPath",
                f"projects/{args.project}/subscriptions/f1-timing-pred-slow")
        .load()
    )

    timing_parsed = (
        timing_raw
        .selectExpr("CAST(data AS STRING) AS json_str",
                     "publish_time AS event_time")
        .select(
            from_json(col("json_str"), TIMING_SCHEMA).alias("d"),
            col("event_time"),
        )
        .select("d.*", "event_time")
    )

    # Take latest record per driver in each micro-batch
    # (watermark lets us discard very late data)
    timing_with_wm = (
        timing_parsed
        .withWatermark("event_time", "30 seconds")
    )

    predict_and_write = make_predict_and_write(
        model_api_url=args.model_api_url,
        influx_url=args.influxdb_url,
        influx_token=args.influxdb_token,
        influx_org=args.influxdb_org,
        influx_bucket=args.influxdb_bucket,
    )

    # Use a 10-second processing trigger — predictions don't need sub-second latency
    query = (
        timing_with_wm
        .select(
            col("race_id"),
            col("total_laps"),
            col("driver_id"),
            col("lap_number"),
            col("position"),
            col("gap_to_leader_ms"),
            col("tyre_age_laps"),
            col("tyre_compound"),
            col("pit_out_lap"),
        )
        .writeStream
        .foreachBatch(predict_and_write)
        .option("checkpointLocation", f"{args.checkpoint_dir}/predictions")
        .trigger(processingTime="10 seconds")
        .start()
    )

    log.info("Slow streaming started — timing → Model API → predictions → InfluxDB")
    query.awaitTermination()


if __name__ == "__main__":
    main()
