resource "google_project_service" "cloudrun_api" {
  project = var.project_id
  service = "run.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry_api" {
  project = var.project_id
  service = "artifactregistry.googleapis.com"

  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = "f1-chubby"
  format        = "DOCKER"

  depends_on = [google_project_service.artifactregistry_api]
}

# Cloud Run service is deployed via CI/CD after the image is built.
# We only create the Artifact Registry repo and enable APIs here.
