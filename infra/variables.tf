variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "gen-lang-client-0314607994"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "asia-southeast1-b"
}

variable "environment" {
  description = "Environment name (dev, prod)"
  type        = string
  default     = "dev"
}

# ---------- Networking ----------
variable "network_name" {
  description = "VPC network name"
  type        = string
  default     = "f1-chubby-vpc"
}

# ---------- Database ----------
variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
}

# ---------- Compute ----------
variable "vm_machine_type" {
  description = "GCE VM machine type"
  type        = string
  default     = "e2-medium"
}

# ---------- TFC Dynamic Provider Credentials ----------
variable "TFC_GCP_PROVIDER_AUTH" {
  description = "TFC dynamic credential: enable GCP provider auth"
  type        = string
  default     = ""
}

variable "TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL" {
  description = "TFC dynamic credential: GCP service account email"
  type        = string
  default     = ""
}
