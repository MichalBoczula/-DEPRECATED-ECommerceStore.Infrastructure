mock_provider "azurerm" {
  override_during = plan
  mock_data "azurerm_client_config" {
    defaults = {
      object_id = "33333333-3333-3333-3333-333333333333"
    }
  }
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-livedocs-archive"
    }
  }
  mock_resource "azurerm_storage_account" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-livedocs-archive/providers/Microsoft.Storage/storageAccounts/stecomldtest"
    }
  }
}
variables {
  subscription_id             = "11111111-1111-1111-1111-111111111111"
  infrastructure_principal_id = "22222222-2222-2222-2222-222222222222"
}
run "persistent_private_archive" {
  command = plan
  assert {
    condition     = azurerm_resource_group.archive.name == "rg-ecommerce-livedocs-archive" && azurerm_management_lock.archive.lock_level == "CanNotDelete" && azurerm_storage_container.reports.container_access_type == "private"
    error_message = "Archive ownership is separate from disposable app state."
  }
  assert {
    condition     = !azurerm_storage_account.archive.shared_access_key_enabled && !azurerm_storage_account.archive.allow_nested_items_to_be_public && azurerm_storage_account.archive.account_replication_type == "LRS" && azurerm_storage_account.archive.blob_properties[0].versioning_enabled
    error_message = "Require private Entra-backed LRS archive with retained versions."
  }
  assert {
    condition     = azurerm_role_assignment.infrastructure_reader.role_definition_name == "Reader" && azurerm_role_assignment.infrastructure_reader.scope == azurerm_storage_account.archive.id
    error_message = "Application CI may only verify archive management metadata."
  }
}
