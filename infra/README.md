# F1-Chubby-Data Infrastructure

Terraform configuration for all GCP resources.

## Prerequisites

- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/install)
- GCP project with billing enabled
- [Terraform Cloud](https://app.terraform.io) account (free tier)

## Quick Start

```bash
cd infra/

# First time: login to Terraform Cloud
terraform login

# Initialize (downloads providers, connects to TFC backend)
terraform init

# Review planned changes
terraform plan -var="db_password=YOUR_SECURE_PASSWORD"

# Apply
terraform apply -var="db_password=YOUR_SECURE_PASSWORD"

# View outputs (connection strings, IPs, etc.)
terraform output
```

## Tear Down

```bash
terraform destroy -var="db_password=ANY_VALUE"
```

## Modules

| Module | Resources |
|--------|-----------|
| `networking` | VPC, subnet, firewall rules (SSH, app ports, internal) |
| `pubsub` | 3 topics + 6 subscriptions (fast/slow per topic) |
| `storage` | 3 GCS buckets (raw, models, replay) |
| `database` | Cloud SQL PostgreSQL (db-f1-micro, stopped by default) |
| `compute` | GCE VM e2-medium with Container-Optimized OS |
| `dataproc` | API enablement + staging bucket |
| `cloudrun` | API enablement + Artifact Registry repo |

## Workload Identity Federation

GitHub Actions authenticate via OIDC — no service account JSON keys stored in secrets.

After `terraform apply`, add these GitHub repo secrets:
- `WIF_PROVIDER` → value of `terraform output wif_provider`
- `WIF_SA_EMAIL` → value of `terraform output github_actions_sa_email`

## Cost Management

- Cloud SQL starts with `activation_policy = NEVER` (stopped). Start manually:
  ```bash
  gcloud sql instances patch f1-chubby-postgres --activation-policy ALWAYS
  ```
- Stop VM when idle: `gcloud compute instances stop f1-chubby-vm --zone asia-southeast1-b`
- Dataproc clusters are created on-demand, not provisioned here.
