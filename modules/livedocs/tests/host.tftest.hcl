mock_provider "azurerm" {}
variables {
  resource_group_name = "rg-ecommerce-dev"
  environment_id      = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/managedEnvironments/cae-ecommerce-dev"
  name                = "ca-ecommerce-dev-livedocs"
  tags                = { managedBy = "Terraform", lifecycle = "disposable" }
  image               = "mb0101/ecommerce-store-livedocs@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
run "small_https_host" {
  command = plan
  assert {
    condition     = azurerm_container_app.host.workload_profile_name == "Consumption" && !azurerm_container_app.host.ingress[0].allow_insecure_connections && azurerm_container_app.host.ingress[0].target_port == 8080
    error_message = "LiveDocs requires Consumption with HTTPS termination on port 8080."
  }
  assert {
    condition     = azurerm_container_app.host.template[0].min_replicas == 0 && azurerm_container_app.host.template[0].max_replicas == 1 && azurerm_container_app.host.template[0].container[0].cpu == 0.25 && azurerm_container_app.host.template[0].container[0].memory == "0.5Gi"
    error_message = "Bound the stateless host to its minimum-cost allocation."
  }
  assert {
    condition     = azurerm_container_app.host.template[0].container[0].startup_probe[0].path == "/health/live" && azurerm_container_app.host.template[0].container[0].readiness_probe[0].path == "/health/ready" && azurerm_container_app.host.template[0].container[0].liveness_probe[0].path == "/health/live"
    error_message = "Explicit probes must match the published container contract."
  }
}
run "mutable_image_rejected" {
  command = plan
  variables { image = "mb0101/ecommerce-store-livedocs:latest" }
  expect_failures = [var.image]
}
