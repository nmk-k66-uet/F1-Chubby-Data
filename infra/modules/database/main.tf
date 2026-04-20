resource "google_sql_database_instance" "postgres" {
  name             = "f1-chubby-postgres"
  project          = var.project_id
  region           = var.region
  database_version = "POSTGRES_15"

  settings {
    tier              = var.db_tier
    activation_policy = "ALWAYS" # must create as ALWAYS, stop manually later to save cost

    ip_configuration {
      ipv4_enabled = true

      authorized_networks {
        name  = "allow-all"
        value = "0.0.0.0/0"
      }
    }

    backup_configuration {
      enabled = false # not needed for demo
    }
  }

  deletion_protection = false # allow terraform destroy
}

resource "google_sql_database" "f1db" {
  name     = "f1chubby"
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "admin" {
  name     = "f1admin"
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}
