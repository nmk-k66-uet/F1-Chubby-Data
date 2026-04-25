# Dedicated service account for the VM
resource "google_service_account" "f1_vm" {
  project      = var.project_id
  account_id   = "f1-vm-sa"
  display_name = "F1 Chubby VM Service Account"
}

resource "google_compute_address" "f1_static_ip" {
  name    = "f1-chubby-static-ip"
  project = var.project_id
  region  = var.region
}

resource "google_compute_instance" "f1_vm" {
  name         = "f1-chubby-vm"
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type

  tags = ["f1-vm"]

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64"
      size  = 50
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = var.subnet_id
    access_config {
      nat_ip = google_compute_address.f1_static_ip.address
    }
  }

  metadata = {
    enable-oslogin = "TRUE"

    user-data = <<-EOF
      #cloud-config
      package_update: true

      runcmd:
      - curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
      - sh /tmp/get-docker.sh
      - systemctl enable docker
      - systemctl start docker
      - |
        # Write .env to a fixed global path so any OS Login user (incl. GitHub Actions SA) can find it
        mkdir -p /opt/f1chubby
        cat > /opt/f1chubby/.env <<DOTENV
        GEMINI_API_KEY=${var.gemini_api_key}
        GCS_CACHE_BUCKET=${var.gcs_cache_bucket}
        GCS_MODELS_BUCKET=${var.gcs_models_bucket}
        GCP_PROJECT_ID=${var.project_id}
        TIMING_VIZ_SUB=${var.timing_viz_sub}
        TIMING_PRED_SUB=${var.timing_pred_sub}
        RC_VIZ_SUB=${var.rc_viz_sub}
        DOTENV
        chmod 644 /opt/f1chubby/.env
      - echo "F1 Chubby VM ready. Docker installed via get-docker.sh."
    EOF
  }

  service_account {
    email  = google_service_account.f1_vm.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  allow_stopping_for_update = true
}
