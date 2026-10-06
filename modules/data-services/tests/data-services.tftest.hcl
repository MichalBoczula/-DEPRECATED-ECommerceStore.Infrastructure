mock_provider "azurerm" {}
variables {
  resource_group_name  = "rg-ecommerce-dev"
  location             = "northeurope"
  tenant_id            = "22222222-2222-2222-2222-222222222222"
  subnet_id            = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.Network/virtualNetworks/vnet-ecommerce-dev/subnets/aca"
  storage_account_name = "stecommercedev1234567890"
  key_vault_name       = "kv-ecom-dev-123456789012"
  tags                 = { lifecycle = "disposable", managedBy = "Terraform" }
}
run "private_disposable_file_services" {
  command = plan
  assert {
    condition     = azurerm_storage_account.business.account_replication_type == "LRS" && !azurerm_storage_account.business.shared_access_key_enabled && !azurerm_storage_account.business.allow_nested_items_to_be_public && alltrue([for container in azurerm_storage_container.files : container.container_access_type == "private"])
    error_message = "Business files require LRS and private Entra-only containers."
  }
  assert {
    condition     = one(azurerm_storage_account.business.network_rules).default_action == "Deny" && one(azurerm_key_vault.business.network_acls).default_action == "Deny" && one(azurerm_key_vault.business.network_acls).virtual_network_subnet_ids == toset([var.subnet_id])
    error_message = "File services must allow only the ACA subnet, with no workstation rule."
  }
  assert {
    condition     = azurerm_key_vault.business.sku_name == "standard" && azurerm_key_vault.business.rbac_authorization_enabled && !azurerm_key_vault.business.purge_protection_enabled && azurerm_key_vault.business.soft_delete_retention_days == 7
    error_message = "Use a disposable Standard RBAC vault that can be purged on teardown."
  }
}
