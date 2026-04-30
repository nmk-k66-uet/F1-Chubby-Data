#!/usr/bin/env bash
set -euo pipefail

PROJECT="gen-lang-client-0314607994"
ZONE="asia-southeast1-b"
VM_NAME="f1-chubby-vm"

usage() {
  echo "Usage: $0 {start|stop|status}"
  exit 1
}

[[ $# -eq 1 ]] || usage

case "$1" in
  start)
    echo "Starting VM..."
    gcloud compute instances start "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --quiet
    echo "Done."
    ;;
  stop)
    echo "Stopping VM..."
    gcloud compute instances stop "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --quiet
    echo "Done."
    ;;
  status)
    echo "=== VM ==="
    gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --format="table(name, status, machineType.basename(), networkInterfaces[0].accessConfigs[0].natIP)"
    ;;
  *)
    usage
    ;;
esac
