FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for matplotlib, psycopg2, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements-streamlit.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY .streamlit/ .streamlit/
COPY core/ core/
COPY components/ components/
COPY pages/ pages/
COPY assets/ assets/
COPY sql/ sql/

ENV MODEL_API_URL=http://model-api:8080
ENV INFLUXDB_URL=http://influxdb:8086

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
