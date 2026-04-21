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
      image = "projects/cos-cloud/global/images/family/cos-stable"
      size  = 30
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

    # Container-Optimized OS: use cloud-init to install docker-compose
    user-data = <<-EOF
      #cloud-config
      write_files:
      - path: /etc/systemd/system/f1-services.service
        permissions: '0644'
        content: |
          [Unit]
          Description=F1 Chubby Services
          After=docker.service
          Requires=docker.service

          [Service]
          Type=oneshot
          RemainAfterExit=yes
          ExecStart=/bin/true

          [Install]
          WantedBy=multi-user.target

      runcmd:
      - echo "F1 Chubby VM ready. Docker available via COS."
    EOF
  }

  service_account {
    scopes = [
      "cloud-platform",
    ]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  allow_stopping_for_update = true
}
