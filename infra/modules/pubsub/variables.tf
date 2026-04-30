variable "project_id" {
  type = string
}

variable "topic_names" {
  description = "List of Pub/Sub topic names"
  type        = list(string)
  default     = ["f1-timing", "f1-race-control"]
}

variable "subscription_names" {
  description = "Explicit list of Pub/Sub subscription names"
  type        = list(string)
  default = [
    "f1-timing-viz-fast",
    "f1-timing-pred-slow",
    "f1-race-control-viz-fast",
  ]
}
