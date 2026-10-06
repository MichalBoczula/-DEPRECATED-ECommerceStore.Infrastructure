# Provider capability audit

Audited for D/3 on 2026-10-04. Exact pins and the lock file are the source of
truth; intentional upgrades must repeat this review. CI checks downloaded
provider schemas, while the links below establish the Azure/API intent.

| Dependency / resource | Verified capability | Deployment decision |
| --- | --- | --- |
| Terraform `1.16.5` | Module tests and mock providers | Same exact version in roots, workflows and `.terraform-version` |
| AzureRM `5.8.0`: `azurerm_mongo_cluster` | `compute_tier` includes `Free` in provider documentation; attribute exists in schema | Candidate only. Check offer/region eligibility in D/6; verify application Mongo features in D/9 |
| AzureRM `5.8.0`: `azurerm_mssql_database` | Schema lacks `use_free_limit` and `free_limit_exhaustion_behavior` | Serverless/autopause alone does not configure the SQL Free offer |
| AzAPI `2.13.0`: `azapi_resource` | Accepts API resource `type` and `body` | D/6 uses SQL free-limit properties and the DocumentDB Free creation contract |
| Azure SQL API `2023-08-01` | Database properties include `useFreeLimit` and `freeLimitExhaustionBehavior` | Require `useFreeLimit=true` and `freeLimitExhaustionBehavior="AutoPause"`; do not silently continue into paid overage |

D/6 implements and tests the AzAPI SQL body, SKU and region policy, with live
management API readback after apply. AzureRM and AzAPI must not both own the same
database. These capabilities do not prove the subscription can claim a free
offer or that the applications work with it. No price guarantee is made by
the pins or mock tests.

D/6 live correction on 2026-10-06: the `2026-06-01` Mongo create API rejected
an administrator body without `userName`; supply both username and password.
SQL server creation returned `ProvisioningDisabled` in North Europe for the
operator's subscription. `candidate_sql_location` overrides SQL only and is
carried through plan validation, management readback and teardown; changing
it does not relocate Mongo or the shared application environment. Availability
must be checked for the active subscription; a successful mock plan proves
neither regional capacity nor Free-offer eligibility.

## Primary sources

- [AzureRM 5.8.0 Mongo cluster documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/website/docs/r/mongo_cluster.html.markdown)
- [AzureRM 5.8.0 SQL database implementation/schema](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/internal/services/mssql/mssql_database_resource.go)
- [AzAPI 2.13.0 release](https://github.com/Azure/terraform-provider-azapi/releases/tag/v2.13.0)
- [Azure SQL database API properties](https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases)
- [Terraform mock providers](https://developer.hashicorp.com/terraform/language/tests/mocking)
- [Terraform machine-readable test plans](https://developer.hashicorp.com/terraform/internals/machine-readable-ui)

- [Mongo Bicep creation contract](https://learn.microsoft.com/en-us/azure/documentdb/quickstart-bicep)
- [SQL subscription edition availability](https://learn.microsoft.com/en-us/cli/azure/sql/db#az-sql-db-list-editions)
