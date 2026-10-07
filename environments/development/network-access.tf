# D/7: stable resource keys allow obsolete ACL entries to be removed on refresh.
locals {
  database_aca_rules = var.enable_database_access ? var.database_aca_ipv4 : toset([])
}

resource "azurerm_mssql_firewall_rule" "aca" {
  for_each         = local.database_aca_rules
  name             = "aca-${replace(each.key, ".", "-")}"
  server_id        = azurerm_mssql_server.database_candidate[0].id
  start_ip_address = each.key
  end_ip_address   = each.key
}

resource "azapi_resource" "mongo_aca_firewall" {
  for_each  = local.database_aca_rules
  type      = "Microsoft.DocumentDB/mongoClusters/firewallRules@2026-06-01"
  name      = "aca-${replace(each.key, ".", "-")}"
  parent_id = azapi_resource.mongo_candidate[0].id
  body = {
    properties = {
      startIpAddress = each.key
      endIpAddress   = each.key
    }
  }
}

output "network_access" {
  description = "Non-secret D/7 discovery and readback inputs; backend acceptance remains D/9."
  value = var.enable_shared_environment || var.enable_livedocs ? {
    environment_id          = module.consumption[0].id
    environment_name        = module.consumption[0].name
    discovery_app           = var.enable_livedocs ? "ca-${module.context.name_prefix}-livedocs" : null
    discovery_apps          = concat(var.enable_livedocs ? ["ca-${module.context.name_prefix}-livedocs"] : [], var.enable_business_apps ? sort(values(local.business_names)) : [])
    discovery_jobs          = var.enable_business_runtime ? [azurerm_container_app_job.database_gate[0].name, azurerm_container_app_job.invoice_probe[0].name] : []
    database_access_enabled = var.enable_database_access
    aca_ipv4                = sort(tolist(local.database_aca_rules))
    candidate = var.enable_database_candidate ? {
      sql_server    = azurerm_mssql_server.database_candidate[0].name
      sql_database  = azapi_resource.sql_candidate[0].name
      sql_location  = var.candidate_sql_location
      mongo_cluster = azapi_resource.mongo_candidate[0].name
    } : null
  } : null
}
