output "vm_name" {
  value = google_compute_instance.f1_vm.name
}

output "vm_external_ip" {
  value = google_compute_instance.f1_vm.network_interface[0].access_config[0].nat_ip
}

output "vm_internal_ip" {
  value = google_compute_instance.f1_vm.network_interface[0].network_ip
}

output "vm_zone" {
  value = google_compute_instance.f1_vm.zone
}
