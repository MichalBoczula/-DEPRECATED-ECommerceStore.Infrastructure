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

run "database_candidate_free_only" {
  command = plan
  variables {
    enable_database_candidate = true
    candidate_suffix          = "reviewd6"
    candidate_sql_password    = "MockOnly-NotASecret-123!"
    candidate_mongo_password  = "MockOnly-NotASecret-456!"
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
