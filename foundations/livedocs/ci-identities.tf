# LD/5: CI-only archive access. Neither identity is attached to the ACA host.
resource "azurerm_user_assigned_identity" "products_archive_writer" {
  name                = "id-products-livedocs-writer"
  resource_group_name = azurerm_resource_group.archive.name
  location            = var.location
  tags                = local.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_user_assigned_identity" "livedocs_archive_reader" {
  name                = "id-livedocs-archive-reader"
  resource_group_name = azurerm_resource_group.archive.name
  location            = var.location
  tags                = local.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_federated_identity_credential" "products_archive_writer" {
  name                      = "github-products-master"
  user_assigned_identity_id = azurerm_user_assigned_identity.products_archive_writer.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:MichalBoczula/ProductsCatalog:ref:refs/heads/master"
  lifecycle { prevent_destroy = true }
}

resource "azurerm_federated_identity_credential" "livedocs_archive_reader" {
  for_each                  = toset(["livedocs-archive-build", "livedocs-archive-pr"])
  name                      = "github-${each.value}"
  user_assigned_identity_id = azurerm_user_assigned_identity.livedocs_archive_reader.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:MichalBoczula/ECommerceStore.LiveDocs:environment:${each.value}"
  lifecycle { prevent_destroy = true }
}

resource "azurerm_role_assignment" "products_archive_writer" {
  scope                            = azurerm_storage_container.reports.id
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.products_archive_writer.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  lifecycle { prevent_destroy = true }
}

resource "azurerm_role_assignment" "livedocs_archive_reader" {
  scope                            = azurerm_storage_container.reports.id
  role_definition_name             = "Storage Blob Data Reader"
  principal_id                     = azurerm_user_assigned_identity.livedocs_archive_reader.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  lifecycle { prevent_destroy = true }
}

output "products_livedocs_client_id" {
  value = azurerm_user_assigned_identity.products_archive_writer.client_id
}
output "livedocs_reader_client_id" {
  value = azurerm_user_assigned_identity.livedocs_archive_reader.client_id
}
output "livedocs_tenant_id" {
  value = data.azurerm_client_config.operator.tenant_id
}
output "livedocs_subscription_id" {
  value = var.subscription_id
}
