variable "resource_group_name" { type = string }
variable "environment_id" { type = string }
variable "name" { type = string }
variable "tags" { type = map(string) }
variable "image" {
  type = string
  validation {
    condition     = can(regex("^mb0101/ecommerce-store-livedocs@sha256:[a-f0-9]{64}$", var.image))
    error_message = "LiveDocs must use an immutable published digest."
  }
}
resource "azurerm_container_app" "host" {
  name                         = var.name
  container_app_environment_id = var.environment_id
  resource_group_name          = var.resource_group_name
  workload_profile_name        = "Consumption"
  revision_mode                = "Single"
  max_inactive_revisions       = 5
  tags                         = merge(var.tags, { component = "LiveDocs" })
  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    min_replicas = 0
    max_replicas = 1
    http_scale_rule {
      name                = "http"
      concurrent_requests = 10
    }
    container {
      name   = "livedocs"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"
      startup_probe {
        transport               = "HTTP"
        path                    = "/health/live"
        port                    = 8080
        interval_seconds        = 2
        timeout                 = 2
        failure_count_threshold = 30
      }
      readiness_probe {
        transport               = "HTTP"
        path                    = "/health/ready"
        port                    = 8080
        initial_delay           = 3
        interval_seconds        = 5
        timeout                 = 2
        failure_count_threshold = 3
        success_count_threshold = 1
      }
      liveness_probe {
        transport               = "HTTP"
        path                    = "/health/live"
        port                    = 8080
        initial_delay           = 10
        interval_seconds        = 10
        timeout                 = 2
        failure_count_threshold = 3
      }
    }
  }
  # Infrastructure is the sole host/image owner; no CLI delivery or ignore_changes.
}
output "id" { value = azurerm_container_app.host.id }
output "portal_url" { value = "https://${azurerm_container_app.host.ingress[0].fqdn}/livedoc/" }
