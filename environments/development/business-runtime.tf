# D/9: one identity per app, plus bounded verification jobs in the same environment.
locals {
  business_release = jsondecode(file("${path.module}/../../releases/development.json"))
  business_keys    = toset(["products", "users", "invoice", "payments", "bff"])
  business_names   = { for key in local.business_keys : key => "ca-${module.context.name_prefix}-${key}" }
  business_urls = var.enable_business_runtime ? {
    for key, name in local.business_names : key => "https://${name}${key == "bff" ? "" : ".internal"}.${module.consumption[0].default_domain}"
  } : {}
  business_allocations = {
    products = { cpu = 0.25, memory = "0.5Gi" }
    users    = { cpu = 0.25, memory = "0.5Gi" }
    invoice  = { cpu = 1.0, memory = "2Gi" }
    payments = { cpu = 0.25, memory = "0.5Gi" }
    bff      = { cpu = 0.25, memory = "0.5Gi" }
  }
  business_secret_keys = {
    products = "products_connection"
    users    = "users_connection"
    invoice  = "invoice_connection"
    payments = "payments_connection"
  }
  runtime_secret_grants = merge(
    { for app, key in local.business_secret_keys : app => { identity = app, secret = local.secret_names[key] } },
    { gate_sql = { identity = "gate", secret = local.secret_names.products_connection },
    gate_mongo = { identity = "gate", secret = local.secret_names.users_connection } }
  )
  business_plain_env = var.enable_business_runtime ? {
    products = { Database__ApplyMigrations = "false" }
    users    = { MongoDbSettings__DatabaseName = local.mongo_databases.users }
    invoice = {
      MongoDbSettings__DatabaseName             = local.mongo_databases.invoice
      ExternalServices__ProductCatalog__BaseUrl = "${local.business_urls.products}/"
    }
    payments = {
      PAYMENTS_ENVIRONMENT           = "development"
      PAYMENTS_MONGODB_DATABASE_NAME = local.mongo_databases.payments
      PAYMENTS_ORDERS_API_BASE_URL   = "${local.business_urls.invoice}/"
      PAYMENTS_STRIPE_ENABLED        = "false"
    }
    bff = {
      GatewaySettings__BaseUrl                                                        = local.business_urls.bff
      "ReverseProxy__Clusters__products-cluster__Destinations__destination1__Address" = "${local.business_urls.products}/"
      "ReverseProxy__Clusters__users-cluster__Destinations__destination1__Address"    = "${local.business_urls.users}/"
      "ReverseProxy__Clusters__orders-cluster__Destinations__destination1__Address"   = "${local.business_urls.invoice}/"
      "ReverseProxy__Clusters__payments-cluster__Destinations__destination1__Address" = "${local.business_urls.payments}/"
    }
  } : {}
  business_secret_env = {
    products = "ConnectionStrings__ProductCatalogDb"
    users    = "MongoDbSettings__ConnectionString"
    invoice  = "MongoDbSettings__ConnectionString"
    payments = "PAYMENTS_MONGODB_CONNECTION_STRING"
  }
  dotnet_env = {
    ASPNETCORE_URLS                     = "http://+:8080"
    ASPNETCORE_ENVIRONMENT              = "Production"
    ASPNETCORE_FORWARDEDHEADERS_ENABLED = "true"
  }
}

resource "azurerm_user_assigned_identity" "business" {
  for_each            = var.enable_business_runtime ? setunion(local.business_keys, toset(["gate"])) : toset([])
  name                = "id-${module.context.name_prefix}-${each.key}"
  resource_group_name = local.retained_resource_group_name
  location            = var.location
  tags                = module.context.tags
}

resource "azurerm_role_assignment" "business_secret" {
  for_each                         = var.enable_business_runtime ? local.runtime_secret_grants : {}
  scope                            = "${module.data_services[0].key_vault_id}/secrets/${each.value.secret}"
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_user_assigned_identity.business[each.value.identity].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# D/12 implements the adapters; grant only the owning service's private container.
resource "azurerm_role_assignment" "business_blob" {
  for_each                         = var.enable_business_runtime ? { products = "photos", invoice = "invoices" } : {}
  scope                            = module.data_services[0].containers[each.value]
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.business[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_container_app" "business" {
  for_each                     = var.enable_business_apps ? local.business_keys : toset([])
  name                         = local.business_names[each.key]
  container_app_environment_id = module.consumption[0].id
  resource_group_name          = local.retained_resource_group_name
  workload_profile_name        = "Consumption"
  revision_mode                = "Single"
  max_inactive_revisions       = 2
  tags                         = merge(module.context.tags, { component = each.key })
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.business[each.key].id]
  }
  dynamic "secret" {
    for_each = each.key == "bff" ? {} : { connection = local.secret_names[local.business_secret_keys[each.key]] }
    content {
      name                = secret.key
      identity            = azurerm_user_assigned_identity.business[each.key].id
      key_vault_secret_id = "${module.data_services[0].key_vault_uri}secrets/${secret.value}"
    }
  }
  ingress {
    external_enabled           = each.key == "bff"
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    min_replicas = 0
    max_replicas = 1
    http_scale_rule {
      name                = "http"
      concurrent_requests = 10
    }
    container {
      name   = each.key
      image  = local.business_release.applications[each.key].image
      cpu    = local.business_allocations[each.key].cpu
      memory = local.business_allocations[each.key].memory
      dynamic "env" {
        for_each = merge(each.key == "payments" ? {} : local.dotnet_env, local.business_plain_env[each.key], {
          AZURE_CLIENT_ID = azurerm_user_assigned_identity.business[each.key].client_id
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = each.key == "bff" ? {} : { connection = local.business_secret_env[each.key] }
        content {
          name        = env.value
          secret_name = env.key
        }
      }
      startup_probe {
        transport               = "HTTP"
        path                    = local.business_release.applications[each.key].runtime.startup
        port                    = 8080
        interval_seconds        = 5
        timeout                 = 5
        failure_count_threshold = 120
      }
      liveness_probe {
        transport               = "HTTP"
        path                    = local.business_release.applications[each.key].runtime.liveness
        port                    = 8080
        initial_delay           = 10
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
      }
      readiness_probe {
        transport               = "HTTP"
        path                    = local.business_release.applications[each.key].runtime.readiness
        port                    = 8080
        interval_seconds        = 10
        timeout                 = 10
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }
  }
  depends_on = [azurerm_role_assignment.business_secret, azurerm_role_assignment.business_blob]
  # Key Vault values are never written in configuration; image/environment drift remains managed.
}

resource "azurerm_container_app_job" "database_gate" {
  count                        = var.enable_business_runtime ? 1 : 0
  name                         = "job-${module.context.name_prefix}-database-gate"
  location                     = var.location
  resource_group_name          = local.retained_resource_group_name
  container_app_environment_id = module.consumption[0].id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 1800
  replica_retry_limit          = 0
  tags                         = module.context.tags
  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.business["gate"].id]
  }
  dynamic "secret" {
    for_each = { sql = local.secret_names.products_connection, mongo = local.secret_names.users_connection }
    content {
      name                = secret.key
      identity            = azurerm_user_assigned_identity.business["gate"].id
      key_vault_secret_id = "${module.data_services[0].key_vault_uri}secrets/${secret.value}"
    }
  }
  template {
    container {
      name   = "gate"
      image  = var.database_gate_image
      cpu    = 1.0
      memory = "2Gi"
      env {
        name        = "D6_SQL_CONNECTION_STRING"
        secret_name = "sql"
      }
      env {
        name        = "D6_MONGO_CONNECTION_STRING"
        secret_name = "mongo"
      }
      dynamic "env" {
        for_each = {
          D6_SQL_HOST   = azurerm_mssql_server.database_candidate[0].fully_qualified_domain_name
          D6_MONGO_HOST = "${azapi_resource.mongo_candidate[0].name}.mongocluster.cosmos.azure.com"
          D9_MODE       = "database"
          D9_APPS       = jsonencode(local.business_urls)
          D9_RUN_ID     = "manual-unbound"
        }
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.business_secret]
}

resource "azurerm_container_app_job" "invoice_probe" {
  count                        = var.enable_business_runtime ? 1 : 0
  name                         = "job-${module.context.name_prefix}-invoice-probe"
  location                     = var.location
  resource_group_name          = local.retained_resource_group_name
  container_app_environment_id = module.consumption[0].id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 300
  replica_retry_limit          = 0
  tags                         = module.context.tags
  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }
  template {
    container {
      name    = "invoice-probe"
      image   = local.business_release.applications.invoice.image
      cpu     = local.business_allocations.invoice.cpu
      memory  = local.business_allocations.invoice.memory
      command = ["pwsh", "-NoProfile", "-Command", file("${path.module}/../../verification/database-gate/invoice-probe.ps1")]
      env {
        name  = "D9_RUN_ID"
        value = "manual-unbound"
      }
    }
  }
}

output "business_runtime" {
  description = "D/9 safe names, identities and immutable images; no secret values or backend acceptance claim."
  value = var.enable_business_runtime ? {
    environment_id = module.consumption[0].id
    apps_enabled   = var.enable_business_apps
    release_id     = local.business_release.releaseId
    apps = { for key in local.business_keys : key => {
      name         = local.business_names[key]
      url          = local.business_urls[key]
      image        = local.business_release.applications[key].image
      identity_id  = azurerm_user_assigned_identity.business[key].id
      principal_id = azurerm_user_assigned_identity.business[key].principal_id
    } }
    gate          = { name = azurerm_container_app_job.database_gate[0].name, image = var.database_gate_image }
    invoice_probe = { name = azurerm_container_app_job.invoice_probe[0].name, image = local.business_release.applications.invoice.image }
    candidate = { sql_server = azurerm_mssql_server.database_candidate[0].name, sql_database = azapi_resource.sql_candidate[0].name,
    sql_location = var.candidate_sql_location, mongo_cluster = azapi_resource.mongo_candidate[0].name }
  } : null
}
