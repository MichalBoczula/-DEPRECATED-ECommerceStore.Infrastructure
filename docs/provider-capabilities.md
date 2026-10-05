# Provider capability audit

Audited for D/3 on 2026-10-04. Exact pins and the lock file are the source of
truth; intentional upgrades must repeat this review. CI checks downloaded
provider schemas, while the links below establish the Azure/API intent.

| Dependency / resource | Verified capability | Deployment decision |
| --- | --- | --- |
| Terraform `1.16.5` | Module tests and mock providers | Same exact version in roots, workflows and `.terraform-version` |
| AzureRM `5.8.0`: `azurerm_mongo_cluster` | `compute_tier` includes `Free` in provider documentation; attribute exists in schema | Candidate only. Check application Mongo features, offer/region eligibility and current pricing in D/6 |
| AzureRM `5.8.0`: `azurerm_mssql_database` | Schema lacks `use_free_limit` and `free_limit_exhaustion_behavior` | Serverless/autopause alone does not configure the SQL Free offer |
| AzAPI `2.13.0`: `azapi_resource` | Accepts API resource `type` and `body` | Use Azure SQL API free-limit properties in D/8 after offer validation |
| Azure SQL API `2023-08-01` | Database properties include `useFreeLimit` and `freeLimitExhaustionBehavior` | Require `useFreeLimit=true` and `freeLimitExhaustionBehavior="AutoPause"`; do not silently continue into paid overage |

AzAPI is pinned now; its SQL resource body, SKU and region checks will be
implemented and tested in D/8. AzureRM and AzAPI must not both own the same
database. These capabilities do not prove the subscription can claim a free
offer or that the applications work with it. No price guarantee is made by
the pins or mock tests.

## Primary sources

- [AzureRM 5.8.0 Mongo cluster documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/website/docs/r/mongo_cluster.html.markdown)
- [AzureRM 5.8.0 SQL database implementation/schema](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/internal/services/mssql/mssql_database_resource.go)
- [AzAPI 2.13.0 release](https://github.com/Azure/terraform-provider-azapi/releases/tag/v2.13.0)
- [Azure SQL database API properties](https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases)
- [Terraform mock providers](https://developer.hashicorp.com/terraform/language/tests/mocking)
- [Terraform machine-readable test plans](https://developer.hashicorp.com/terraform/internals/machine-readable-ui)
