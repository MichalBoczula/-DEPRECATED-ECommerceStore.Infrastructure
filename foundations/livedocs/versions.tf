terraform {
  required_version = "= 1.16.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "= 5.8.0" }
  }
  # Same external account, dedicated archive-state container/key; operator CLI.
  backend "azurerm" { use_azuread_auth = true }
}
provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
  features {}
}
