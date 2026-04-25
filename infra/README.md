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
| `pubsub` | 3 topics + 6 subscriptions (fast/slow per topic) |
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
