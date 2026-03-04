output "mcp_server_url" {
  description = "HTTPS URL for the MCP server."
  value       = "https://${azurerm_container_app.mcp_server.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Azure Container Registry login server."
  value       = azurerm_container_registry.server.login_server
}

output "server_resource_group" {
  description = "Server resource group name."
  value       = azurerm_resource_group.server.name
}

output "workloads_resource_group" {
  description = "Workloads resource group name."
  value       = azurerm_resource_group.workloads.name
}
