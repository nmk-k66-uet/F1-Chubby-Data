# Dataproc cluster is created on-demand by GitHub Actions CI.
# This module enables the API and creates a staging bucket.

resource "google_project_service" "dataproc_api" {
  project = var.project_id
  service = "dataproc.googleapis.com"

  disable_on_destroy = false
}

resource "google_storage_bucket" "dataproc_staging" {
  name          = "${var.staging_bucket}-${var.project_id}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  force_destroy               = true
}
