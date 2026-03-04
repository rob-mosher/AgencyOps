provider "azurerm" {
  features {}
}

variable "container_instances" {
  description = "Map of container instances to provision, keyed by name."
  type = map(object({
    image      = string
    cpu        = number
    memory_gb  = number
    gpu_sku    = optional(string, "")
    gpu_count  = optional(number, 0)
    purpose    = string
    namespace  = string
    location   = optional(string, "eastus")
  }))
  default = {}
}

variable "resource_group_name" {
  description = "Resource group for workload resources."
  type        = string
  default     = "agencyops-workloads"
}

data "azurerm_resource_group" "workloads" {
  name = var.resource_group_name
}

resource "azurerm_container_group" "workload" {
  for_each = var.container_instances

  name                = each.key
  location            = each.value.location
  resource_group_name = data.azurerm_resource_group.workloads.name
  os_type             = "Linux"
  restart_policy      = "Always"

  container {
    name   = each.key
    image  = each.value.image
    cpu    = each.value.cpu
    memory = each.value.memory_gb

    dynamic "gpu" {
      for_each = each.value.gpu_count > 0 ? [1] : []
      content {
        count = each.value.gpu_count
        sku   = each.value.gpu_sku
      }
    }

    ports {
      port     = 80
      protocol = "TCP"
    }
  }

  tags = {
    "agencyops.purpose"   = each.value.purpose
    "agencyops.namespace" = each.value.namespace
    "agencyops.managed"   = "true"
  }
}
