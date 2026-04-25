# Production Deployment Runbook

Step-by-step guide to deploy the full F1-Chubby-Data system on Google Cloud Platform.

## Prerequisites

- GCP project with billing enabled
- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/install) installed
- [Terraform Cloud](https://app.terraform.io) account (free tier)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- GitHub repository with Actions enabled

---

## Step 1: Provision Infrastructure

All GCP resources are managed by Terraform in the `infra/` directory.

```bash
cd infra

# Login to Terraform Cloud
terraform login

# Initialize (downloads providers, connects to TFC backend)
terraform init

# Review what will be created
terraform plan

# Apply
terraform apply

# Save outputs — you'll need these for GitHub secrets and VM config
terraform output
```

### What Gets Created

| Module | Resources |
|--------|-----------|
| **networking** | VPC `f1-chubby-vpc`, subnet, firewall rules (SSH, ports 80/8080/8086, internal) |
| **pubsub** | 2 topics (`f1-timing`, `f1-race-control`) × 2 subscriptions each (fast/slow) |
| **storage** | 3 GCS buckets: `f1chubby-cache-*`, `f1chubby-model-*`, `f1chubby-replay-*` |

| **compute** | GCE VM `f1-chubby-vm` (e2-medium, Container-Optimized OS) + static IP + service account |
| **dataproc** | API enablement + staging bucket (clusters created on-demand) |
| **cloudrun** | API enablement + Artifact Registry repo (future use) |

### Key Outputs

| Output | Used For |
|--------|----------|
| `vm_external_ip` | Dashboard URL, SSH access |
| `wif_provider` | GitHub Actions secret `WIF_PROVIDER` |
| `github_actions_sa_email` | GitHub Actions secret `WIF_SA_EMAIL` |
| `gcs_cache_bucket` | Streamlit `GCS_BUCKET` env var |
| `gcs_models_bucket` | Model API `GCS_BUCKET` env var |

---

## Step 2: Configure GitHub Secrets

The CI/CD pipelines authenticate to GCP via **Workload Identity Federation** (OIDC — no JSON keys).

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** and add:

| Secret | Value |
|--------|-------|
| `WIF_PROVIDER` | `terraform output -raw wif_provider` |
| `WIF_SA_EMAIL` | `terraform output -raw github_actions_sa_email` |

---

## Step 3: Configure VM Environment

SSH into the VM and create the production `.env` file:

```bash
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b

# Create the env file (referenced by deploy-vm.yml workflow)
sudo mkdir -p /opt/f1chubby
sudo tee /opt/f1chubby/.env << 'EOF'
# InfluxDB
INFLUXDB_TOKEN=f1chubby-influx-token
INFLUXDB_PASSWORD=<CHANGE_THIS>

# Model Serving
USE_GCS=true
GCS_MODELS_BUCKET=f1chubby-model-gen-lang-client-0314607994

# Streamlit
GCS_BUCKET=f1chubby-cache-gen-lang-client-0314607994
LOCAL_MODE=false

# Gemini (optional — for AI tactical briefing)
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
EOF
```

---

## Step 4: Upload Data Assets

Upload data assets manually using `gsutil`:

```bash
# Upload FastF1 cache to GCS
gsutil -m cp -r f1_cache/* gs://f1chubby-cache-gen-lang-client-0314607994/

# Upload trained model artifacts
gsutil -m cp assets/Models/*.pkl gs://f1chubby-model-gen-lang-client-0314607994/
```

---

## Step 5: Deploy Application

### Automatic (recommended)

Push to the `main` branch. The `deploy-vm.yml` workflow will:
1. Authenticate to GCP via Workload Identity Federation
2. `gcloud compute scp` all app files to `~/app/` on the VM
3. SSH into the VM, copy `.env` from `/opt/f1chubby/.env`, run `docker compose up -d --build`

Path filter: only triggers when relevant files change (see `.github/workflows/deploy-vm.yml`).

### Manual

```bash
# SSH into VM
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b

# Pull latest code (or scp files manually)
cd ~/app

# Deploy
cp /opt/f1chubby/.env .env
sudo docker compose up -d --build --remove-orphans
```

---

## Step 6: Train / Retrain Models

Trigger the `deploy-dataproc.yml` workflow:
1. Go to **Actions** → **Deploy Dataproc Jobs** → **Run workflow**
2. Select `training` as the job type
3. The workflow creates a Dataproc cluster (auto-deletes after 10 min idle), submits the training pipeline, and uploads new `.pkl` files to GCS

After training completes, restart the model-api container on the VM to pick up new models:

```bash
gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b -- \
  "cd ~/app && sudo docker compose restart model-api"
```

---

## Step 7: Run Live Demo

1. **Ensure VM is running:**
   ```bash
   ./scripts/infra.sh start
   ```

2. **Start streaming consumers** (if not already in docker-compose.yml):
   ```bash
   gcloud compute ssh f1-chubby-vm --zone asia-southeast1-b -- \
     "cd ~/app && sudo docker compose up -d streaming-fast streaming-slow"
   ```

3. **Run race simulation** (from your local machine or the VM):
   ```bash
   python scripts/simulate_race_to_influxdb.py --speed 3
   ```

4. **Open dashboard:** `http://<VM_EXTERNAL_IP>` (or `http://f1.thedblaster.id.vn` if DNS is configured)

5. Navigate to a race → **Live Race** tab to see real-time timing tower and ML predictions updating.

6. **Stop when done:**
   ```bash
   ./scripts/infra.sh stop
   ```

---

## CI/CD Pipelines

Four GitHub Actions workflows automate the deployment lifecycle:

### deploy-vm.yml — Application Deployment

- **Trigger:** Push to `main` (path-filtered to app code) or manual dispatch
- **What it does:** Copies app files to GCE VM via `gcloud compute scp`, runs `docker compose up --build`
- **Auth:** Workload Identity Federation (OIDC, no JSON keys)

### deploy-dataproc.yml — Spark Job Submission

- **Trigger:** Manual dispatch only (`workflow_dispatch`)
- **Input:** Job type (`training`)
- **What it does:** Uploads Spark files to GCS staging bucket, creates/reuses Dataproc cluster, submits PySpark job
- **Cluster:** Single-node `e2-standard-4`, auto-deletes after 10 min idle

### terraform.yml — Infrastructure Changes

- **Trigger:** Push to `main` or PR touching `infra/**`
- **What it does:** On PR → `terraform plan` (comment on PR). On merge → `terraform apply` via Terraform Cloud
- **Auth:** Terraform Cloud OIDC to GCP (separate from GitHub Actions WIF)

---

## Environment Variables Reference

### Streamlit Container

| Variable | Production Value | Description |
|----------|-----------------|-------------|
| `MODEL_API_URL` | `http://model-api:8080` | Model API internal URL |
| `INFLUXDB_URL` | `http://influxdb:8086` | InfluxDB internal URL |
| `INFLUXDB_TOKEN` | `f1chubby-influx-token` | InfluxDB admin token |
| `INFLUXDB_ORG` | `f1chubby` | InfluxDB organization |
| `INFLUXDB_BUCKET` | `live_race` | InfluxDB bucket name |
| `GCS_BUCKET` | `f1chubby-cache-<project_id>` | GCS cache bucket for FastF1 data |
| `LOCAL_MODE` | `false` | `true` = skip InfluxDB/Model API, use FastF1 only |
| `GEMINI_API_KEY` | *(user-provided)* | Google Gemini API key for tactical briefing |

### Model API Container

| Variable | Production Value | Description |
|----------|-----------------|-------------|
| `MODEL_DIR` | `/app/models` | Directory for `.pkl` model files |
| `GCS_BUCKET` | `f1chubby-model-<project_id>` | GCS bucket with model artifacts |
| `USE_GCS` | `true` | Download models from GCS on startup |

### InfluxDB Container

| Variable | Production Value | Description |
|----------|-----------------|-------------|
| `DOCKER_INFLUXDB_INIT_MODE` | `setup` | Auto-initialize on first run |
| `DOCKER_INFLUXDB_INIT_USERNAME` | `admin` | Admin username |
| `DOCKER_INFLUXDB_INIT_PASSWORD` | *(from .env)* | Admin password |
| `DOCKER_INFLUXDB_INIT_ORG` | `f1chubby` | Organization name |
| `DOCKER_INFLUXDB_INIT_BUCKET` | `live_race` | Default bucket |
| `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` | *(from .env)* | Admin API token |

### Streaming Consumers

| Variable | Value | Description |
|----------|-------|-------------|
| `--project` | `gen-lang-client-0314607994` | GCP project ID (CLI arg) |
| `--influxdb-url` | `http://influxdb:8086` | InfluxDB URL (CLI arg) |
| `--influxdb-token` | *(from .env)* | InfluxDB token (CLI arg) |
| `--model-api-url` | `http://model-api:8080` | Model API URL (slow path only, CLI arg) |

---

## Cost Management

| Resource | Strategy |
|----------|----------|
| **GCE VM** | Stop when idle: `./scripts/infra.sh stop` |
| **Dataproc** | Created on-demand with `--max-idle 600s` (auto-deletes after 10 min) |
| **GCS** | Minimal cost; no lifecycle rules needed for current data volume |

---

← Back to [ReadMe.md](../ReadMe.md)
