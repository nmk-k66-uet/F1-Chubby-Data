FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for matplotlib, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (cached unless requirements change)
COPY requirements-streamlit.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy assets before code (assets change less frequently than code)
COPY assets/ assets/

# Copy static config
COPY .streamlit/ .streamlit/

# Copy application code (most frequently changed)
COPY main.py .
COPY core/ core/
COPY components/ components/
COPY pages/ pages/

ENV MODEL_API_URL=http://model-api:8080
ENV INFLUXDB_URL=http://influxdb:8086

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
