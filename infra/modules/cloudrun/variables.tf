variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image" {
  description = "Container image for Streamlit (empty = placeholder, deploy later)"
  type        = string
  default     = ""
}

variable "cloudsql_connection_name" {
  description = "Cloud SQL connection name for Cloud SQL proxy"
  type        = string
  default     = ""
}
