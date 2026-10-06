mock_provider "azurerm" {
  mock_resource "azurerm_virtual_network" {
    defaults = { name = "vnet-ecommerce-dev" }
  }
  mock_resource "azurerm_subnet" {
    defaults = { id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.Network/virtualNetworks/vnet-ecommerce-dev/subnets/aca" }
  }
}
variables {
  resource_group_name = "rg-ecommerce-dev"
  name_prefix         = "ecommerce-dev"
  location            = "northeurope"
  tags                = { managedBy = "Terraform" }
}
run "shared_consumption_environment" {
  command = plan
  assert {
    condition     = toset(azurerm_subnet.host.service_endpoints) == toset(["Microsoft.Storage", "Microsoft.KeyVault"])
    error_message = "Prepare supported Storage/Key Vault endpoints; cross-region SQL uses IP ACLs."
  }
  assert {
    condition     = length(azurerm_container_app_environment.host.workload_profile) == 1 && one(azurerm_container_app_environment.host.workload_profile).workload_profile_type == "Consumption" && azurerm_container_app_environment.host.logs_destination == null
    error_message = "Use only Consumption and streaming logs; no dedicated profile or analytics workspace."
  }
  assert {
    condition     = !azurerm_container_app_environment.host.internal_load_balancer_enabled && azurerm_subnet.host.address_prefixes == tolist(["10.42.0.0/23"])
    error_message = "Use an external environment with the explicit ACA subnet."
  }
}
