#!/usr/bin/env bash
set -euo pipefail

PROJECT="gen-lang-client-0314607994"
ZONE="asia-southeast1-b"
SQL_INSTANCE="f1-chubby-postgres"
VM_NAME="f1-chubby-vm"

usage() {
  echo "Usage: $0 {start|stop|status}"
  exit 1
}

[[ $# -eq 1 ]] || usage

case "$1" in
  start)
    echo "Starting Cloud SQL instance..."
    gcloud sql instances patch "$SQL_INSTANCE" --activation-policy ALWAYS --project="$PROJECT" --quiet
    echo "Starting VM..."
    gcloud compute instances start "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --quiet
    echo "Done. Both resources are starting."
    ;;
  stop)
    echo "Stopping Cloud SQL instance..."
    gcloud sql instances patch "$SQL_INSTANCE" --activation-policy NEVER --project="$PROJECT" --quiet
    echo "Stopping VM..."
    gcloud compute instances stop "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --quiet
    echo "Done. Both resources are stopped."
    ;;
  status)
    echo "=== Cloud SQL ==="
    gcloud sql instances describe "$SQL_INSTANCE" --project="$PROJECT" --format="table(name, state, settings.tier, ipAddresses[0].ipAddress)"
    echo ""
    echo "=== VM ==="
    gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --format="table(name, status, machineType.basename(), networkInterfaces[0].accessConfigs[0].natIP)"
    ;;
  *)
    usage
    ;;
esac
