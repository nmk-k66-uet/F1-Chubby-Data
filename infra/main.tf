terraform {
  cloud {
    organization = "duyle"
    workspaces {
      name = "f1-chubby-data"
    }
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
  project = var.project_id
  region  = var.region
}

# --- Enable required APIs ---

resource "google_project_service" "apis" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
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

module "database" {
  source = "./modules/database"

  project_id  = var.project_id
  region      = var.region
  db_tier     = var.db_tier
  db_password = var.db_password

  depends_on = [google_project_service.apis]
}

module "compute" {
  source = "./modules/compute"

  project_id       = var.project_id
  region           = var.region
  zone             = var.zone
  machine_type     = var.vm_machine_type
  subnet_id        = module.networking.subnet_id
  gemini_api_key    = google_apikeys_key.gemini.key_string
  gcs_cache_bucket  = "f1chubby-cache-${var.project_id}"
  gcs_models_bucket = "f1chubby-models-${var.project_id}"

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

# --- Workload Identity Federation for GitHub Actions ---

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == 'nmk-k66-uet/F1-Chubby-Data'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service account for GitHub Actions
resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "github-actions-sa"
  display_name = "GitHub Actions Service Account"
}

# Allow GitHub Actions to impersonate the service account
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/nmk-k66-uet/F1-Chubby-Data"
}

# Grant the service account necessary roles
locals {
  sa_roles = [
    "roles/storage.admin",
    "roles/pubsub.admin",
    "roles/cloudsql.admin",
    "roles/compute.admin",
    "roles/dataproc.admin",
    "roles/run.admin",
    "roles/artifactregistry.admin",
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.apiKeysAdmin",
  ]
}

resource "google_project_iam_member" "github_actions_roles" {
  for_each = toset(local.sa_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# --- Workload Identity Federation for Terraform Cloud ---

resource "google_iam_workload_identity_pool" "tfc" {
  project                   = var.project_id
  workload_identity_pool_id = "terraform-cloud"
  display_name              = "Terraform Cloud"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "tfc" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.tfc.workload_identity_pool_id
  workload_identity_pool_provider_id = "tfc-oidc"
  display_name                       = "Terraform Cloud OIDC"

  attribute_mapping = {
    "google.subject"                        = "assertion.sub"
    "attribute.aud"                         = "assertion.aud"
    "attribute.terraform_workspace_id"      = "assertion.terraform_workspace_id"
    "attribute.terraform_workspace_name"    = "assertion.terraform_workspace_name"
    "attribute.terraform_organization_id"   = "assertion.terraform_organization_id"
    "attribute.terraform_organization_name" = "assertion.terraform_organization_name"
    "attribute.terraform_run_phase"         = "assertion.terraform_run_phase"
    "attribute.terraform_full_workspace"    = "assertion.terraform_full_workspace"
  }

  attribute_condition = "assertion.sub.startsWith(\"organization:duyle:project:\")"

  oidc {
    issuer_uri = "https://app.terraform.io"
  }
}

# Service account for Terraform Cloud
resource "google_service_account" "tfc" {
  project      = var.project_id
  account_id   = "terraform-cloud-sa"
  display_name = "Terraform Cloud Service Account"
}

# Allow Terraform Cloud to impersonate the service account
resource "google_service_account_iam_member" "tfc_wif_binding" {
  service_account_id = google_service_account.tfc.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.tfc.name}/*"
}

# Grant TFC service account the same roles
resource "google_project_iam_member" "tfc_roles" {
  for_each = toset(local.sa_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.tfc.email}"
}

# --- VM Service Account: GCS access ---

resource "google_storage_bucket_iam_member" "vm_bucket_access" {
  for_each = module.storage.bucket_names

  bucket = each.value
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${module.compute.vm_service_account_email}"
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
