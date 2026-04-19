resource "google_storage_bucket" "buckets" {
  for_each = toset(var.bucket_names)

  name          = "${each.value}-${var.project_id}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  force_destroy = true # allow terraform destroy to delete non-empty buckets
}
