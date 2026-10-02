terraform {
  required_version = "= 1.16.5"

  # The independent bootstrap repository owns this store and its identity.
  # The workflow supplies the account/container; the dev key is fixed there.
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}
