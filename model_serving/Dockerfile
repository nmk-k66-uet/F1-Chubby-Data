FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN mkdir -p models

ENV MODEL_DIR=/app/models
ENV GCS_BUCKET=f1chubby-model-gen-lang-client-0314607994
ENV USE_GCS=true

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
