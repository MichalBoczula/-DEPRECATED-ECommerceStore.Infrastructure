data "azurerm_client_config" "data_services" {
  count = var.enable_data_services ? 1 : 0
}

locals {
  # Deterministic names survive destroy/recreate; no random suffix or extra state.
  data_services_hash = var.enable_data_services ? sha256("${data.azurerm_client_config.data_services[0].subscription_id}/${local.retained_resource_group_name}") : ""
  mongo_databases = {
    users    = "ecommerce-store-users-db"
    invoice  = "ecommerce-store-invoice-db"
    payments = "ecommerce_store_payments"
  }
  secret_names = {
    products_connection = "products-sql-connection"
    users_connection    = "users-mongo-connection"
    invoice_connection  = "invoice-mongo-connection"
    payments_connection = "payments-mongo-connection"
    stripe_key          = "stripe-secret-key"
    stripe_webhook      = "stripe-webhook-secret"
  }
}

module "data_services" {
  count                = var.enable_data_services ? 1 : 0
  source               = "../../modules/data-services"
  resource_group_name  = local.retained_resource_group_name
  location             = var.location
  tenant_id            = data.azurerm_client_config.data_services[0].tenant_id
  subnet_id            = module.consumption[0].subnet_id
  storage_account_name = "st${replace(module.context.name_prefix, "-", "")}${substr(local.data_services_hash, 0, 10)}"
  key_vault_name       = "kv-${replace(module.context.name_prefix, "ecommerce", "ecom")}-${substr(local.data_services_hash, 0, 12)}"
  tags                 = module.context.tags
}

output "data_services" {
  description = "Non-secret D/8 endpoints and logical database/secret contracts. Values are never exported."
  value = var.enable_data_services ? {
    storage_account_id   = module.data_services[0].storage_account_id
    storage_account_name = module.data_services[0].storage_account_name
    blob_endpoint        = module.data_services[0].blob_endpoint
    containers           = module.data_services[0].containers
    key_vault_id         = module.data_services[0].key_vault_id
    key_vault_name       = module.data_services[0].key_vault_name
    key_vault_uri        = module.data_services[0].key_vault_uri
    subnet_id            = module.consumption[0].subnet_id
    mongo_databases      = local.mongo_databases
    secret_names         = local.secret_names
    sql = var.enable_database_candidate ? {
      server   = azurerm_mssql_server.database_candidate[0].name
      database = azapi_resource.sql_candidate[0].name
    } : null
  } : null
}
