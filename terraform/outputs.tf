output "container_ids" {
  description = "Map of container names to their IDs"
  value       = { for k, v in docker_container.workload : k => v.id }
}

output "container_names" {
  description = "List of managed container names"
  value       = keys(docker_container.workload)
}
