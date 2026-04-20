variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "staging_bucket" {
  description = "GCS bucket name for Dataproc staging (without gs:// prefix)"
  type        = string
}
