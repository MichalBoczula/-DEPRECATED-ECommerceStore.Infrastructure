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
print("Provider interfaces checked: AzureRM Mongo compute tier; AzAPI SQL free-offer body support. Live eligibility and Mongo transactions remain D/6 gates.")
