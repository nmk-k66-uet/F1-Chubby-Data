# F1-Chubby-Data Infrastructure

Terraform configuration for all GCP resources.

## Prerequisites

- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/install)
- GCP project with billing enabled
- A GCS bucket for Terraform state (created once, before first `terraform init`)

## Bootstrap

On a fresh GCP project, enable the minimum APIs that Terraform and the GCS backend need:

```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  storage.googleapis.com \
  --project=gen-lang-client-0314607994
```

Then create the state bucket:

```bash
gcloud storage buckets create gs://f1chubby-tfstate-gen-lang-client-0314607994 \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --public-access-prevention

# Enable versioning to protect state history
gcloud storage buckets update gs://f1chubby-tfstate-gen-lang-client-0314607994 \
  --versioning
```

## Quick Start

```bash
cd infra/

# Authenticate to GCP
gcloud auth application-default login

# Set quota project (required by apikeys.googleapis.com)
gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>

# Initialize (downloads providers, connects to GCS backend)
terraform init

# Review planned changes
terraform plan

# Apply
terraform apply

# View outputs (connection strings, IPs, etc.)
terraform output
```

## Tear Down

```bash
terraform destroy
```

## Modules

| Module | Resources |
|--------|-----------|
| `networking` | VPC, subnet, firewall rules (SSH, app ports, internal) |
| `pubsub` | 2 topics + 3 subscriptions (fast path × 2, slow path × 1) |
| `storage` | 3 GCS buckets (raw, models, replay) |

| `compute` | GCE VM e2-medium with Container-Optimized OS |
| `dataproc` | API enablement + staging bucket |
| `cloudrun` | API enablement + Artifact Registry repo |

## Workload Identity Federation

GitHub Actions authenticate via OIDC — no service account JSON keys stored in secrets.

After `terraform apply`, add these GitHub repo secrets:
- `WIF_PROVIDER` → value of `terraform output wif_provider`
- `WIF_SA_EMAIL` → value of `terraform output github_actions_sa_email`

## Cost Management

- Stop VM when idle: `gcloud compute instances stop f1-chubby-vm --zone asia-southeast1-b`
- Dataproc clusters are created on-demand, not provisioned here.

---

For the full end-to-end production deployment guide (including CI/CD, VM configuration, and data upload), see [docs/deployment.md](../docs/deployment.md).

← Back to [ReadMe.md](../ReadMe.md)
