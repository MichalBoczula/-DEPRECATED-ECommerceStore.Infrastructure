# CI never receives Azure credentials. Mock every configured Azure provider.
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "11111111-1111-1111-1111-111111111111"
      tenant_id       = "22222222-2222-2222-2222-222222222222"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    override_during = plan
    defaults = {
      id             = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/managedEnvironments/cae-ecommerce-dev"
      default_domain = "mock-domain.northeurope.azurecontainerapps.io"
    }
  }
  mock_resource "azurerm_subnet" {
    defaults = { id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.Network/virtualNetworks/vnet-ecommerce-dev/subnets/aca" }
  }
}

run "business_stage" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_livedocs           = true
    enable_database_candidate = true
    enable_data_services      = true
    enable_business_runtime   = true
    database_gate_image       = "mb0101/ecommerce-store-database-gate@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    candidate_suffix          = "reviewd7"
    candidate_sql_location    = "francecentral"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
  }
  assert {
    condition     = length(azurerm_user_assigned_identity.business) == 6 && length(azurerm_role_assignment.business_secret) == 6 && length(azurerm_role_assignment.business_blob) == 2 && length(azurerm_container_app.business) == 0 && length(azurerm_container_app_job.database_gate) == 1 && length(azurerm_container_app_job.invoice_probe) == 1
    error_message = "Stage bounded jobs and narrow identities without launching business apps."
  }
}

run "business_apps" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_livedocs           = true
    enable_database_candidate = true
    enable_database_access    = true
    database_aca_ipv4         = ["20.40.60.80", "20.40.60.81"]
    enable_data_services      = true
    enable_business_runtime   = true
    enable_business_apps      = true
    database_gate_image       = "mb0101/ecommerce-store-database-gate@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    candidate_suffix          = "reviewd7"
    candidate_sql_location    = "francecentral"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
  }
  assert {
    condition     = length(azurerm_container_app.business) == 5 && azurerm_container_app.business["bff"].ingress[0].external_enabled && alltrue([for app, resource in azurerm_container_app.business : !resource.ingress[0].external_enabled if app != "bff"])
    error_message = "Deploy exactly five apps with only BFF public business ingress."
  }
  assert {
    condition     = alltrue([for resource in azurerm_container_app.business : resource.template[0].min_replicas == 0 && resource.template[0].max_replicas == 1 && resource.workload_profile_name == "Consumption"]) && azurerm_container_app.business["invoice"].template[0].container[0].memory == "2Gi"
    error_message = "Preserve scale-to-zero and Invoice browser allocation."
  }
}

run "business_apps_without_runtime_rejected" {
  command = plan
  variables { enable_business_apps = true }
  expect_failures = [var.enable_business_apps]
}

run "business_runtime_without_foundation_rejected" {
  command = plan
  variables {
    enable_business_runtime = true
    database_gate_image     = "mb0101/ecommerce-store-database-gate@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.enable_business_runtime]
}
mock_provider "azapi" {}

run "development_contract" {
  command = plan
  assert {
    condition     = length(module.data_services) == 0
    error_message = "D/8 file services must remain disabled by default."
  }
  assert {
    condition     = length(module.consumption) == 0 && length(azurerm_mssql_firewall_rule.aca) == 0 && length(azapi_resource.mongo_aca_firewall) == 0
    error_message = "D/7 network and database firewall access must remain disabled by default."
  }
  assert {
    condition     = length(azurerm_mssql_server.database_candidate) == 0 && length(azapi_resource.mongo_candidate) == 0
    error_message = "D/6 must not provision a database by default."
  }
  assert {
    condition     = output.deployment_context.environment == "development" && output.deployment_context.resource_group_name == "rg-ecommerce-dev"
    error_message = "The development root must retain its fixed environment and bootstrap-owned resource group."
  }
  assert {
    condition     = output.deployment_context.tags.lifecycle == "disposable" && output.deployment_context.tags.costProfile == "minimal"
    error_message = "Development resource modules must receive disposable minimum-cost metadata."
  }
}

run "data_services_without_docs" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_data_services      = true
  }
  assert {
    condition     = length(module.data_services) == 1 && length(module.livedocs) == 0 && length(azapi_resource.mongo_candidate) == 0 && keys(output.data_services.containers) == ["invoices", "photos"]
    error_message = "File services must be independently staged without extra apps/databases."
  }
}

run "data_services_with_databases" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_livedocs           = true
    enable_data_services      = true
    enable_database_candidate = true
    candidate_suffix          = "reviewd7"
    candidate_sql_location    = "francecentral"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
  }
  assert {
    condition     = output.data_services.sql.database == "products-gate" && output.data_services.mongo_databases.users == "ecommerce-store-users-db" && output.data_services.mongo_databases.invoice == "ecommerce-store-invoice-db" && output.data_services.mongo_databases.payments == "ecommerce_store_payments" && length(azapi_resource.mongo_candidate) == 1 && !output.network_access.database_access_enabled
    error_message = "Reuse D/6 databases, reserve separate Mongo names and keep access explicitly staged."
  }
}

run "data_services_without_subnet_rejected" {
  command = plan
  variables { enable_data_services = true }
  expect_failures = [var.enable_data_services]
}

run "shared_environment_without_docs" {
  command = plan
  variables { enable_shared_environment = true }
  assert {
    condition     = length(module.consumption) == 1 && length(module.livedocs) == 0 && !output.network_access.database_access_enabled
    error_message = "The shared environment must be independent of LiveDocs and leave database access disabled."
  }
}

run "aca_database_access" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_livedocs           = true
    enable_database_candidate = true
    enable_database_access    = true
    candidate_suffix          = "reviewd7"
    candidate_sql_location    = "francecentral"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
    database_aca_ipv4         = ["20.40.60.80", "20.40.60.81"]
  }
  assert {
    condition     = azurerm_mssql_server.database_candidate[0].public_network_access_enabled && azapi_resource.mongo_candidate[0].body.properties.publicNetworkAccess == "Enabled" && length(azurerm_mssql_firewall_rule.aca) == 2 && length(azapi_resource.mongo_aca_firewall) == 2
    error_message = "Only explicitly enabled access may create one SQL/Mongo rule for each observed ACA IPv4."
  }
  assert {
    condition     = alltrue([for rule in azurerm_mssql_firewall_rule.aca : rule.start_ip_address == rule.end_ip_address]) && azapi_resource.sql_candidate[0].body.properties.freeLimitExhaustionBehavior == "AutoPause" && !output.database_candidate.selected
    error_message = "Keep single-IP rules, SQL AutoPause and provisional backend status."
  }
}

run "access_without_addresses_rejected" {
  command = plan
  variables {
    enable_shared_environment = true
    enable_database_candidate = true
    enable_database_access    = true
    candidate_suffix          = "reviewd7"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
  }
  expect_failures = [var.enable_database_access]
}

run "broad_azure_rule_rejected" {
  command = plan
  variables { database_aca_ipv4 = ["0.0.0.0"] }
  expect_failures = [var.database_aca_ipv4]
}

run "database_candidate_free_only" {
  command = plan
  variables {
    enable_database_candidate = true
    candidate_suffix          = "reviewd6"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
    candidate_sql_location    = "westeurope"
  }
  assert {
    condition     = azurerm_mssql_server.database_candidate[0].location == "westeurope" && azapi_resource.sql_candidate[0].location == "westeurope" && azapi_resource.mongo_candidate[0].location == "northeurope" && output.deployment_context.location == "northeurope" && output.database_candidate.sql_location == "westeurope"
    error_message = "The SQL-only region override must leave Mongo and the shared development context in North Europe."
  }
  assert {
    condition     = azapi_resource.mongo_candidate[0].body.properties.administrator.userName == "d6operator"
    error_message = "Mongo ARM creation requires an explicit administrator username."
  }
  assert {
    condition     = azapi_resource.mongo_candidate[0].body.properties.compute.tier == "Free" && azapi_resource.mongo_candidate[0].body.properties.storage.sizeGb == 32 && azapi_resource.mongo_candidate[0].body.properties.sharding.shardCount == 1 && azapi_resource.mongo_candidate[0].body.properties.highAvailability.targetMode == "Disabled"
    error_message = "D/6 must use an explicit Free Mongo cluster without HA."
  }
  assert {
    condition     = azapi_resource.sql_candidate[0].body.properties.useFreeLimit && azapi_resource.sql_candidate[0].body.properties.freeLimitExhaustionBehavior == "AutoPause" && azapi_resource.sql_candidate[0].body.properties.maxSizeBytes == 34359738368
    error_message = "D/6 must use the SQL free offer and pause at exhaustion."
  }
  assert {
    condition     = !azurerm_mssql_server.database_candidate[0].public_network_access_enabled && azapi_resource.mongo_candidate[0].body.properties.publicNetworkAccess == "Disabled" && !output.database_candidate.selected
    error_message = "D/6 must keep public database access disabled and leave backend acceptance to deployment checks."
  }
}

run "livedocs_uses_shared_environment" {
  command = plan
  variables { enable_livedocs = true }
  assert {
    condition     = length(module.consumption) == 1 && length(module.livedocs) == 1 && module.consumption[0].name == "cae-ecommerce-dev" && output.livedocs.commit_sha == "a11d396ad01f1324569c69483e870fa8b9c23cf7"
    error_message = "D/4 must use one shared environment and a recorded release."
  }
}
