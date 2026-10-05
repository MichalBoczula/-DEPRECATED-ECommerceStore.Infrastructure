provider "azurerm" {
  features {}
  # Subscription registrations belong to the persistent foundation operator.
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}

provider "azapi" {
  # D/6 uses this for SQL's explicit free-offer properties.
  enable_preflight = true
}
