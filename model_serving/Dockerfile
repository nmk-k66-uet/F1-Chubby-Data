FROM python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN mkdir -p models

ENV MODEL_DIR=/app/models
ENV GCS_BUCKET=f1chubby-model-${GCP_PROJECT_ID:-<PROJECT_ID>}
ENV USE_GCS=true

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
