terraform {
  required_version = "= 1.16.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.8.0"
    }
    # AzureRM lacks SQL useFreeLimit/freeLimitExhaustionBehavior in this version.
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
  }

  # The independent state store is created outside application Terraform.
  # The workflow supplies the account/container; the dev key is fixed there.
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}
