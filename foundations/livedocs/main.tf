variable "subscription_id" {
  type = string
  validation {
    condition     = can(regex("^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$", var.subscription_id))
    error_message = "Use the selected Azure subscription UUID."
  }
}
variable "infrastructure_principal_id" {
  type = string
  validation {
    condition     = can(regex("^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$", var.infrastructure_principal_id))
    error_message = "Use TerraformState's deployment principal UUID."
  }
}
variable "location" {
  type    = string
  default = "northeurope"
}
locals {
  tags = { project = "ECommerceStore", component = "LiveDocs", managedBy = "Terraform", lifecycle = "persistent-archive" }
}
data "azurerm_client_config" "operator" {}
resource "azurerm_resource_group" "archive" {
  name     = "rg-ecommerce-livedocs-archive"
  location = var.location
  tags     = local.tags
  lifecycle { prevent_destroy = true }
}
resource "azurerm_storage_account" "archive" {
  name                            = "stecomld${substr(sha256(var.subscription_id), 0, 14)}"
  resource_group_name             = azurerm_resource_group.archive.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  public_network_access           = "Enabled"
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  default_to_oauth_authentication = true
  tags                            = local.tags
  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
  lifecycle { prevent_destroy = true }
}
resource "azurerm_storage_container" "reports" {
  name                  = "livedocs"
  storage_account_id    = azurerm_storage_account.archive.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
}
resource "azurerm_role_assignment" "operator" {
  scope                = azurerm_storage_account.archive.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.operator.object_id
  lifecycle { prevent_destroy = true }
}
resource "azurerm_management_lock" "archive" {
  name       = "protect-livedocs-archive"
  scope      = azurerm_resource_group.archive.id
  lock_level = "CanNotDelete"
  lifecycle { prevent_destroy = true }
  depends_on = [azurerm_storage_container.reports, azurerm_role_assignment.operator]
}
resource "azurerm_role_assignment" "infrastructure_reader" {
  scope                            = azurerm_storage_account.archive.id
  role_definition_name             = "Reader"
  principal_id                     = var.infrastructure_principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  lifecycle { prevent_destroy = true }
}
output "archive_storage_account" { value = azurerm_storage_account.archive.name }
