# D/6 candidate only: disabled until explicitly configured. Same disposable state.
resource "azurerm_mssql_server" "database_candidate" {
  count                         = var.enable_database_candidate ? 1 : 0
  name                          = "sql-${module.context.name_prefix}-d6-${var.candidate_suffix}"
  resource_group_name           = local.retained_resource_group_name
  location                      = var.candidate_sql_location
  version                       = "12.0"
  administrator_login           = "d6operator"
  administrator_login_password  = var.candidate_sql_password
  minimum_tls_version           = "1.2"
  public_network_access_enabled = false
  tags                          = module.context.tags
}
# AzureRM 5.8.0 cannot express the Free offer: one owner, explicit AzAPI body.
resource "azapi_resource" "sql_candidate" {
  count     = var.enable_database_candidate ? 1 : 0
  type      = "Microsoft.Sql/servers/databases@2023-08-01"
  name      = "products-gate"
  parent_id = azurerm_mssql_server.database_candidate[0].id
  location  = var.candidate_sql_location
  tags      = module.context.tags
  body = {
    sku = { name = "GP_S_Gen5_2", tier = "GeneralPurpose", family = "Gen5", capacity = 2 }
    properties = {
      useFreeLimit                     = true
      freeLimitExhaustionBehavior      = "AutoPause"
      autoPauseDelay                   = 60
      minCapacity                      = 0.5
      maxSizeBytes                     = 34359738368
      requestedBackupStorageRedundancy = "Local"
      licenseType                      = "LicenseIncluded"
      zoneRedundant                    = false
    }
  }
}
# ARM creation requires administrator.userName, including the Free tier.
data "azurerm_client_config" "database_candidate" {
  count = var.enable_database_candidate ? 1 : 0
}
resource "azapi_resource" "mongo_candidate" {
  count     = var.enable_database_candidate ? 1 : 0
  type      = "Microsoft.DocumentDB/mongoClusters@2026-06-01"
  name      = "mongo-${module.context.name_prefix}-d6-${var.candidate_suffix}"
  parent_id = "/subscriptions/${data.azurerm_client_config.database_candidate[0].subscription_id}/resourceGroups/${local.retained_resource_group_name}"
  location  = var.location
  tags      = module.context.tags
  body = {
    properties = {
      administrator       = { userName = "d6operator", password = var.candidate_mongo_password }
      authConfig          = { allowedModes = ["NativeAuth"] }
      compute             = { tier = "Free" }
      createMode          = "Default"
      highAvailability    = { targetMode = "Disabled" }
      publicNetworkAccess = "Disabled"
      serverVersion       = "8.0"
      sharding            = { shardCount = 1 }
      storage             = { sizeGb = 32, type = "PremiumSSD" }
    }
  }
}
output "database_candidate" {
  description = "Non-secret candidate names; connection strings/passwords are never exported."
  value = var.enable_database_candidate ? {
    sql_server    = azurerm_mssql_server.database_candidate[0].name
    sql_database  = azapi_resource.sql_candidate[0].name
    mongo_cluster = azapi_resource.mongo_candidate[0].name
    location      = var.location
    sql_location  = var.candidate_sql_location
    selected      = false
  } : null
}
