variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-medium"
}

variable "subnet_id" {
  type = string
}

variable "gemini_api_key" {
  description = "Gemini API key for Streamlit predictor"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gcs_cache_bucket" {
  description = "GCS cache bucket name (full name with project suffix)"
  type        = string
  default     = ""
}

variable "gcs_models_bucket" {
  description = "GCS models bucket name (full name with project suffix)"
  type        = string
  default     = ""
}

variable "timing_viz_sub" {
  description = "Pub/Sub subscription name for fast-path timing"
  type        = string
}

variable "timing_pred_sub" {
  description = "Pub/Sub subscription name for slow-path timing"
  type        = string
}

variable "rc_viz_sub" {
  description = "Pub/Sub subscription name for fast-path race control"
  type        = string
}
