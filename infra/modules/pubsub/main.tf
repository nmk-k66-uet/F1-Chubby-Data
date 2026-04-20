resource "google_pubsub_topic" "topics" {
  for_each = toset(var.topic_names)

  name    = each.value
  project = var.project_id

  message_retention_duration = "86400s" # 1 day
}

locals {
  # Produce a flat map: { "f1-telemetry-viz-fast" = { topic = "f1-telemetry", suffix = "viz-fast" }, ... }
  subscriptions = {
    for pair in setproduct(var.topic_names, var.subscription_suffixes) :
    "${pair[0]}-${pair[1]}" => {
      topic  = pair[0]
      suffix = pair[1]
    }
  }
}

resource "google_pubsub_subscription" "subs" {
  for_each = local.subscriptions

  name    = each.key
  project = var.project_id
  topic   = google_pubsub_topic.topics[each.value.topic].id

  ack_deadline_seconds       = 20
  message_retention_duration = "86400s"

  expiration_policy {
    ttl = "" # never expire
  }
}
