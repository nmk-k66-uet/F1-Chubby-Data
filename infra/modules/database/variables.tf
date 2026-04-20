variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "db_password" {
  type      = string
  sensitive = true
}
