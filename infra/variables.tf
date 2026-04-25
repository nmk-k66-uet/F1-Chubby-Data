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

# ---------- GitHub ----------
variable "github_repo" {
  description = "GitHub repository (owner/repo) for Workload Identity Federation"
  type        = string
  default     = "nmk-k66-uet/F1-Chubby-Data"
}

# ---------- Compute ----------
variable "vm_machine_type" {
  description = "GCE VM machine type"
  type        = string
  default     = "e2-medium"
}
