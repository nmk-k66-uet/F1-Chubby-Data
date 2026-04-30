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
