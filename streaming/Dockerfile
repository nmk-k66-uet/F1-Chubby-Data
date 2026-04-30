FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    google-cloud-pubsub==2.29.0 \
    influxdb-client==1.48.0 \
    requests==2.33.1

COPY streaming_fast.py .
COPY streaming_slow.py .
