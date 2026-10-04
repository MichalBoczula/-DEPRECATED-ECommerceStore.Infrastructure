provider "azurerm" {
  features {}
  # Subscription registrations belong to the persistent foundation operator.
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}

provider "azapi" {
  # D/7 uses this only for SQL's explicit free-offer properties.
  enable_preflight = true
}
