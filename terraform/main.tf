terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

variable "containers" {
  description = "Map of containers to provision, keyed by name"
  type = map(object({
    image       = string
    memory_mb   = number
    gpu_enabled = bool
    purpose     = string
    namespace   = string
  }))
  default = {}
}

resource "docker_image" "workload" {
  for_each = var.containers
  name     = each.value.image
}

resource "docker_container" "workload" {
  for_each = var.containers

  name  = each.key
  image = docker_image.workload[each.key].image_id

  memory = each.value.memory_mb

  runtime = each.value.gpu_enabled ? "nvidia" : "runc"

  labels {
    label = "agencyops.purpose"
    value = each.value.purpose
  }

  labels {
    label = "agencyops.namespace"
    value = each.value.namespace
  }

  labels {
    label = "agencyops.managed"
    value = "true"
  }
}
