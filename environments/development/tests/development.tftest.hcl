# CI never receives Azure credentials. Mock every configured Azure provider.
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "11111111-1111-1111-1111-111111111111"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/managedEnvironments/cae-ecommerce-dev"
    }
  }
}
mock_provider "azapi" {}

run "development_contract" {
  command = plan
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
