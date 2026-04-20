output "instance_name" {
  value = google_sql_database_instance.postgres.name
}

output "connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "public_ip" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "database_name" {
  value = google_sql_database.f1db.name
}

output "db_user" {
  value = google_sql_user.admin.name
}
