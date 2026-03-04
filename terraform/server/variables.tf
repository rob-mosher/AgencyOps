variable "project_name" {
  description = "Project name prefix for all resources."
  type        = string
  default     = "agencyops"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "server_resource_group" {
  description = "Resource group for the MCP server infrastructure."
  type        = string
  default     = "agencyops-server"
}

variable "workloads_resource_group" {
  description = "Resource group for workload resources Claude provisions."
  type        = string
  default     = "agencyops-workloads"
}

variable "acr_name" {
  description = "Azure Container Registry name (globally unique, alphanumeric only)."
  type        = string
}

variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "tenant_id" {
  description = "Azure tenant ID."
  type        = string
}

variable "arm_client_id" {
  description = "Service principal client ID for Terraform azurerm operations."
  type        = string
  sensitive   = true
}

variable "arm_client_secret" {
  description = "Service principal client secret."
  type        = string
  sensitive   = true
}

variable "api_key" {
  description = "API key for MCP server authentication (Bearer token)."
  type        = string
  sensitive   = true
}

variable "azure_monthly_limit" {
  description = "Monthly Azure budget limit in USD."
  type        = number
  default     = 150.0
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    project = "agencyops"
    managed = "terraform"
  }
}
