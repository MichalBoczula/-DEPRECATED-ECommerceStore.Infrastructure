# CI never receives Azure credentials. Mock every configured Azure provider.
mock_provider "azurerm" {}
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
