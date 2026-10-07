#!/usr/bin/env python3
"""Verify the resource interfaces documented for the later free-offer gate."""
import json
import sys

with open(sys.argv[1]) as stream:
    providers = json.load(stream)["provider_schemas"]
azure = providers["registry.terraform.io/hashicorp/azurerm"]["resource_schemas"]
assert "compute_tier" in azure["azurerm_mongo_cluster"]["block"]["attributes"]
sql = azure["azurerm_mssql_database"]["block"]["attributes"]
assert "use_free_limit" not in sql and "free_limit_exhaustion_behavior" not in sql, "Revisit the SQL provider decision when schema capabilities change."
azapi = providers["registry.terraform.io/azure/azapi"]["resource_schemas"]["azapi_resource"]["block"]["attributes"]
assert "body" in azapi and "type" in azapi
endpoint = azure["azurerm_subnet"]["block"]["block_types"]["service_endpoint"]["block"]["attributes"]
assert endpoint["service"]["required"] and "network_identifier" in endpoint
job = azure["azurerm_container_app_job"]["block"]
assert all(name in job["attributes"] for name in ("workload_profile_name", "replica_timeout_in_seconds", "replica_retry_limit", "outbound_ip_addresses"))
assert "manual_trigger_config" in job["block_types"]
secret = job["block_types"]["secret"]["block"]["attributes"]
assert "key_vault_secret_id" in secret and "identity" in secret
print("Provider interfaces checked: AzureRM Mongo compute tier and subnet service_endpoint blocks; AzAPI SQL free-offer body support. Live eligibility remains D/6; Mongo compatibility is verified during D/9 deployment.")
