terraform {
  # Backend configuration: use -backend-config during terraform init
  # Example: terraform init -backend-config="bucket=f1chubby-tfstate-<PROJECT_ID>"
  backend "gcs" {
    prefix = "terraform/state"
  }

  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

# --- Enable required APIs ---

resource "google_project_service" "apis" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "apikeys.googleapis.com",
    "generativelanguage.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

# --- Modules ---

module "networking" {
  source = "./modules/networking"

  project_id   = var.project_id
  region       = var.region
  network_name = var.network_name

  depends_on = [google_project_service.apis]
}

module "pubsub" {
  source = "./modules/pubsub"

  project_id = var.project_id

  depends_on = [google_project_service.apis]
}

module "storage" {
  source = "./modules/storage"

  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "compute" {
  source = "./modules/compute"

  project_id        = var.project_id
  region            = var.region
  zone              = var.zone
  machine_type      = var.vm_machine_type
  subnet_id         = module.networking.subnet_id
  gemini_api_key    = google_apikeys_key.gemini.key_string
  gcs_cache_bucket  = "f1chubby-cache-${var.project_id}"
  gcs_models_bucket = "f1chubby-model-${var.project_id}"
  timing_viz_sub    = module.pubsub.subscription_names_map["f1-timing-viz-fast"]
  timing_pred_sub   = module.pubsub.subscription_names_map["f1-timing-pred-slow"]
  rc_viz_sub        = module.pubsub.subscription_names_map["f1-race-control-viz-fast"]

  depends_on = [google_project_service.apis]
}

module "dataproc" {
  source = "./modules/dataproc"

  project_id     = var.project_id
  region         = var.region
  zone           = var.zone
  subnet_id      = module.networking.subnet_id
  staging_bucket = "f1chubby-dataproc-staging"

  depends_on = [google_project_service.apis]
}

# --- Dataproc Service Account ---

resource "google_service_account" "dataproc" {
  project      = var.project_id
  account_id   = "f1-dataproc-sa"
  display_name = "F1 Dataproc Service Account"

  depends_on = [google_project_service.apis]
}

locals {
  dataproc_sa_roles = [
    "roles/dataproc.worker",
    "roles/pubsub.subscriber",
    "roles/pubsub.publisher",
    "roles/storage.objectViewer",
  ]
}

resource "google_project_iam_member" "dataproc_roles" {
  for_each = toset(local.dataproc_sa_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dataproc.email}"
}

# GitHub Actions SA needs to impersonate Dataproc SA (to create clusters with it)
resource "google_service_account_iam_member" "github_actions_use_dataproc_sa" {
  service_account_id = google_service_account.dataproc.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions.email}"
}

# --- Workload Identity Federation for GitHub Actions ---

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions-v2"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc-v2"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service account for GitHub Actions
resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "github-actions-sa"
  display_name = "GitHub Actions Service Account"

  depends_on = [google_project_service.apis]
}

# Allow GitHub Actions to impersonate the service account
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# Grant the service account necessary roles
locals {
  sa_roles = [
    "roles/storage.admin",
    "roles/pubsub.admin",
    "roles/compute.admin",
    "roles/compute.osAdminLogin",
    "roles/dataproc.admin",
    "roles/run.admin",
    "roles/artifactregistry.admin",
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/serviceusage.apiKeysAdmin",
  ]
}

resource "google_project_iam_member" "github_actions_roles" {
  for_each = toset(local.sa_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# --- VM Service Account: GCS access ---

resource "google_storage_bucket_iam_member" "vm_bucket_access" {
  for_each = module.storage.bucket_names

  bucket = each.value
  role   = "roles/storage.admin"
  member = "serviceAccount:${module.compute.vm_service_account_email}"
}

# --- VM Service Account: Pub/Sub subscriber access ---

resource "google_project_iam_member" "vm_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${module.compute.vm_service_account_email}"
}

# --- Gemini API Key (restricted to Generative Language API) ---

resource "google_apikeys_key" "gemini" {
  project      = var.project_id
  name         = "gemini-streamlit"
  display_name = "Gemini API Key for Streamlit"

  restrictions {
    api_targets {
      service = "generativelanguage.googleapis.com"
    }
  }

  depends_on = [google_project_service.apis]
}
