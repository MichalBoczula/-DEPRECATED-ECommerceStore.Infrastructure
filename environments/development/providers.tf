provider "azurerm" {
  features {}
  # Subscription registrations belong to the persistent foundation operator.
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}

provider "azapi" {
  # Keep normal schema/plan validation. Optional ARM preflight substitutes fake
  # parent IDs when planning a database under a server created in the same apply.
  # Azure validates the real request during apply; the workflow checks Free
  # settings before apply and reads them back afterwards.
  enable_preflight = false
}
