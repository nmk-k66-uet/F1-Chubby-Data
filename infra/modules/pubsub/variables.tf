variable "project_id" {
  type = string
}

variable "topic_names" {
  description = "List of Pub/Sub topic names"
  type        = list(string)
  default     = ["f1-timing", "f1-race-control"]
}

variable "subscription_suffixes" {
  description = "Subscription suffix list per topic"
  type        = list(string)
  default     = ["viz-fast", "pred-slow"]
}
