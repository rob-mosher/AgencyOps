output "container_instance_ids" {
  description = "Map of container instance names to their Azure resource IDs."
  value       = { for k, v in azurerm_container_group.workload : k => v.id }
}

output "container_instance_ips" {
  description = "Map of container instance names to their IP addresses."
  value       = { for k, v in azurerm_container_group.workload : k => v.ip_address }
}
