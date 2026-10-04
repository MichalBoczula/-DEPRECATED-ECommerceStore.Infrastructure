# CI never receives Azure credentials. Mock every configured Azure provider.
mock_provider "azurerm" {
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/managedEnvironments/cae-ecommerce-dev"
    }
  }
}
mock_provider "azapi" {}

run "development_contract" {
  command = plan
  assert {
    condition     = output.deployment_context.environment == "development" && output.deployment_context.resource_group_name == "rg-ecommerce-dev"
    error_message = "The development root must retain its fixed environment and bootstrap-owned resource group."
  }
  assert {
    condition     = output.deployment_context.tags.lifecycle == "disposable" && output.deployment_context.tags.costProfile == "minimal"
    error_message = "Development resource modules must receive disposable minimum-cost metadata."
  }
}

run "livedocs_uses_shared_environment" {
  command = plan
  variables { enable_livedocs = true }
  assert {
    condition     = length(module.consumption) == 1 && length(module.livedocs) == 1 && module.consumption[0].name == "cae-ecommerce-dev" && output.livedocs.commit_sha == "a11d396ad01f1324569c69483e870fa8b9c23cf7"
    error_message = "D/4 must use one shared environment and a recorded release."
  }
}
