output "topic_ids" {
  value = { for k, v in google_pubsub_topic.topics : k => v.id }
}

output "topic_names" {
  value = [for t in google_pubsub_topic.topics : t.name]
}

output "subscription_names" {
  value = [for s in google_pubsub_subscription.subs : s.name]
}
