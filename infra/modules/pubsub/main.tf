resource "google_pubsub_topic" "topics" {
  for_each = toset(var.topic_names)

  name    = each.value
  project = var.project_id

  message_retention_duration = "86400s" # 1 day
}

locals {
  # Map each subscription name to its topic by stripping the last suffix
  subscriptions = {
    for name in var.subscription_names :
    name => regex("^(f1-[a-z-]+?)-(viz-fast|pred-slow)$", name)[0]
  }
}

resource "google_pubsub_subscription" "subs" {
  for_each = local.subscriptions

  name    = each.key
  project = var.project_id
  topic   = google_pubsub_topic.topics[each.value].id

  ack_deadline_seconds       = 20
  message_retention_duration = "86400s"

  expiration_policy {
    ttl = "" # never expire
  }
}
