output "staging_bucket" {
  value = google_storage_bucket.dataproc_staging.name
}
