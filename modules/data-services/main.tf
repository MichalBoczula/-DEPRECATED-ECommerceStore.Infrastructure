variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tenant_id" { type = string }
variable "subnet_id" { type = string }
variable "tags" { type = map(string) }
variable "storage_account_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Use a valid globally unique storage account name."
  }
}
variable "key_vault_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.key_vault_name)) && !strcontains(var.key_vault_name, "--")
    error_message = "Use a valid globally unique Key Vault name."
  }
}

resource "azurerm_storage_account" "business" {
  name                            = var.storage_account_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  access_tier                     = "Hot"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  public_network_access           = "Enabled"
  tags                            = var.tags
  network_rules {
    default_action             = "Deny"
    bypass                     = ["None"]
    ip_rules                   = []
    virtual_network_subnet_ids = [var.subnet_id]
  }
  # Synthetic business files are disposable. No versions or soft-delete retention.
  blob_properties { versioning_enabled = false }
}

resource "azurerm_storage_container" "files" {
  for_each              = toset(["invoices", "photos"])
  name                  = each.key
  storage_account_id    = azurerm_storage_account.business.id
  container_access_type = "private"
}

resource "azurerm_key_vault" "business" {
  name                            = var.key_vault_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  tenant_id                       = var.tenant_id
  sku_name                        = "standard"
  rbac_authorization_enabled      = true
  public_network_access_enabled   = true
  enabled_for_deployment          = false
  enabled_for_disk_encryption     = false
  enabled_for_template_deployment = false
  soft_delete_retention_days      = 7
  purge_protection_enabled        = false
  tags                            = var.tags
  network_acls {
    default_action             = "Deny"
    bypass                     = "None"
    ip_rules                   = []
    virtual_network_subnet_ids = [var.subnet_id]
  }
  # Values are injected outside Terraform. D/9 grants app identities scoped reads.
}

output "storage_account_id" { value = azurerm_storage_account.business.id }
output "storage_account_name" { value = azurerm_storage_account.business.name }
output "blob_endpoint" { value = azurerm_storage_account.business.primary_blob_endpoint }
output "containers" { value = { for name, container in azurerm_storage_container.files : name => container.id } }
output "key_vault_id" { value = azurerm_key_vault.business.id }
output "key_vault_name" { value = azurerm_key_vault.business.name }
output "key_vault_uri" { value = azurerm_key_vault.business.vault_uri }
