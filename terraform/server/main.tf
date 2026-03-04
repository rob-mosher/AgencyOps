provider "azurerm" {
  features {}
}

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "server" {
  name     = var.server_resource_group
  location = var.location
  tags     = var.tags
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "server" {
  name                = "${var.project_name}-logs"
  location            = azurerm_resource_group.server.location
  resource_group_name = azurerm_resource_group.server.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "server" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.server.name
  location            = azurerm_resource_group.server.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Storage for Terraform state persistence
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "data" {
  name                     = "${var.project_name}data"
  resource_group_name      = azurerm_resource_group.server.name
  location                 = azurerm_resource_group.server.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = var.tags
}

resource "azurerm_storage_share" "data" {
  name               = "agencyops-data"
  storage_account_id = azurerm_storage_account.data.id
  quota              = 1 # GB
}

# ---------------------------------------------------------------------------
# Workload resource group (for resources Claude provisions)
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "workloads" {
  name     = var.workloads_resource_group
  location = var.location
  tags     = var.tags
}

# ---------------------------------------------------------------------------
# Container App Environment
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "server" {
  name                       = "${var.project_name}-env"
  location                   = azurerm_resource_group.server.location
  resource_group_name        = azurerm_resource_group.server.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.server.id
  tags                       = var.tags
}

resource "azurerm_container_app_environment_storage" "data" {
  name                         = "agencyops-data"
  container_app_environment_id = azurerm_container_app_environment.server.id
  account_name                 = azurerm_storage_account.data.name
  share_name                   = azurerm_storage_share.data.name
  access_key                   = azurerm_storage_account.data.primary_access_key
  access_mode                  = "ReadWrite"
}

# ---------------------------------------------------------------------------
# Container App (the MCP server)
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "mcp_server" {
  name                         = "${var.project_name}-mcp"
  container_app_environment_id = azurerm_container_app_environment.server.id
  resource_group_name          = azurerm_resource_group.server.name
  revision_mode                = "Single"
  tags                         = var.tags

  template {
    volume {
      name         = "data"
      storage_type = "AzureFile"
      storage_name = azurerm_container_app_environment_storage.data.name
    }

    container {
      name   = "agencyops"
      image  = "${azurerm_container_registry.server.login_server}/agencyops:latest"
      cpu    = 0.5
      memory = "1Gi"

      volume_mounts {
        name = "data"
        path = "/data"
      }

      env {
        name  = "AGENCYOPS_DATA_DIR"
        value = "/data"
      }
      env {
        name  = "AGENCYOPS_TERRAFORM_DIR"
        value = "/app/terraform/workloads"
      }
      env {
        name  = "AGENCYOPS_AZURE_SUBSCRIPTION_ID"
        value = var.subscription_id
      }
      env {
        name  = "AGENCYOPS_AZURE_LOCATION"
        value = var.location
      }
      env {
        name  = "AGENCYOPS_AZURE_RESOURCE_GROUP"
        value = var.workloads_resource_group
      }
      env {
        name  = "AGENCYOPS_AZURE_MONTHLY_LIMIT"
        value = tostring(var.azure_monthly_limit)
      }
      env {
        name        = "AGENCYOPS_API_KEY"
        secret_name = "api-key"
      }
      env {
        name        = "ARM_CLIENT_ID"
        secret_name = "arm-client-id"
      }
      env {
        name        = "ARM_CLIENT_SECRET"
        secret_name = "arm-client-secret"
      }
      env {
        name  = "ARM_TENANT_ID"
        value = var.tenant_id
      }
      env {
        name  = "ARM_SUBSCRIPTION_ID"
        value = var.subscription_id
      }
    }

    min_replicas = 0
    max_replicas = 1
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "http"
    allow_insecure_connections = false

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }

    dynamic "ip_security_restriction" {
      for_each = var.allowed_ip_ranges
      content {
        action           = "Allow"
        ip_address_range = ip_security_restriction.value.ip_address_range
        name             = ip_security_restriction.value.name
      }
    }
  }

  secret {
    name  = "api-key"
    value = var.api_key
  }
  secret {
    name  = "arm-client-id"
    value = var.arm_client_id
  }
  secret {
    name  = "arm-client-secret"
    value = var.arm_client_secret
  }
  secret {
    name  = "acr-password"
    value = azurerm_container_registry.server.admin_password
  }

  registry {
    server               = azurerm_container_registry.server.login_server
    username             = azurerm_container_registry.server.admin_username
    password_secret_name = "acr-password"
  }
}
