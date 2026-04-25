variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "bucket_names" {
  description = "List of GCS bucket names"
  type        = list(string)
  default     = ["f1chubby-raw", "f1chubby-model", "f1chubby-cache"]
}
