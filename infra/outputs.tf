# --- Networking ---
output "vpc_network_name" {
  value = module.networking.network_name
}

# --- Pub/Sub ---
output "pubsub_topics" {
  value = module.pubsub.topic_names
}

output "pubsub_subscriptions" {
  value = module.pubsub.subscription_names
}

# --- Storage ---
output "gcs_buckets" {
  value = module.storage.bucket_names
}

# --- Database ---
output "cloudsql_instance_name" {
  value = module.database.instance_name
}

output "cloudsql_connection_name" {
  value = module.database.connection_name
}

output "cloudsql_public_ip" {
  value = module.database.public_ip
}

output "cloudsql_database" {
  value = module.database.database_name
}

output "cloudsql_user" {
  value = module.database.db_user
}

# --- Compute ---
output "vm_external_ip" {
  value = module.compute.vm_external_ip
}

output "vm_name" {
  value = module.compute.vm_name
}

output "vm_zone" {
  value = module.compute.vm_zone
}

# --- Dataproc ---
output "dataproc_staging_bucket" {
  value = module.dataproc.staging_bucket
}

# --- Workload Identity Federation (GitHub Actions) ---
output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "github_actions_sa_email" {
  value = google_service_account.github_actions.email
}

# --- Workload Identity Federation (Terraform Cloud) ---
output "tfc_wif_provider" {
  description = "TFC Dynamic Provider Credentials: set as TFC_GCP_PROVIDER_AUTH value"
  value       = google_iam_workload_identity_pool_provider.tfc.name
}

output "tfc_sa_email" {
  description = "TFC Dynamic Provider Credentials: set as TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL value"
  value       = google_service_account.tfc.email
}
