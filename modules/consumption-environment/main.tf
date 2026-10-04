variable "resource_group_name" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_virtual_network" "host" {
  name                = "vnet-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = ["10.42.0.0/16"]
  tags                = var.tags
}
resource "azurerm_subnet" "host" {
  name                 = "aca"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.host.name
  address_prefixes     = ["10.42.0.0/23"]
  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}
resource "azurerm_container_app_environment" "host" {
  name                               = "cae-${var.name_prefix}"
  resource_group_name                = var.resource_group_name
  location                           = var.location
  infrastructure_subnet_id           = azurerm_subnet.host.id
  infrastructure_resource_group_name = "rg-${var.name_prefix}-aca-managed"
  internal_load_balancer_enabled     = false
  public_network_access              = "Enabled"
  zone_redundancy_enabled            = false
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
  # Omit logs_destination: stream logs, without a paid ingestion workspace.
  tags = var.tags
}
output "id" { value = azurerm_container_app_environment.host.id }
output "name" { value = azurerm_container_app_environment.host.name }
output "managed_resource_group_name" { value = azurerm_container_app_environment.host.infrastructure_resource_group_name }
