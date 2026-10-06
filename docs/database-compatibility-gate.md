# D/6: provision the free database candidate

Status: the operator reported local creation on 2026-10-06 of SQL server
`sql-ecommerce-dev-d6-mike2026` and database `products-gate` in France Central,
and `mongo-ecommerce-dev-d6-mike2026` in North Europe. Post-apply Free/network
readback has not been supplied. The operator reported the disposable environment
cleared before D/7 on 2026-10-06; this is not D/19 residual-cost evidence. D/6
remains provisional. D/7 configures access from Container Apps; D/9 verifies
real driver compatibility before accepting the backend for the applications.
D/17 covers business flows and D/19 covers destroy/recreate proof. The D/5
application release remains unchanged.

Use the [local PowerShell runbook](local-development.md) for provisioning,
Free readback and teardown against the existing remote state. No GitHub
environment input is required for that route. The workflow instructions below
remain an optional OIDC execution route. The [D/7 local network access](development-network-access.md)
accounts for SQL and ACA being in different regions.

## Candidate and cost boundary

| Candidate | Explicit configuration | Acceptance requirement |
| --- | --- | --- |
| Azure SQL Database | SQL-only `candidate_sql_location` (default North Europe), General Purpose serverless, `useFreeLimit=true`, `freeLimitExhaustionBehavior=AutoPause`, 32 GiB limit, local backup redundancy | The subscription can create the free offer; ARM readback confirms the free settings (D/6); EF Core SQL Server 10.0.1 and Dapper 2.1.66 checks pass from Azure (D/9) |
| Azure DocumentDB Free | North Europe, `Free`, 32 GiB, one shard, HA disabled, Mongo compatibility 8.0, NativeAuth | Terraform creation and Free readback (D/6); unchanged readiness and driver checks from Azure (D/9); recreation proof (D/19) |

Both are **experiments in the existing disposable development state**, container `development-state`, key `ecommerce/development.tfstate`, default workspace. Three managed resources: SQL logical server, SQL database and Mongo cluster. The D/6-only configuration disables public data-plane access on both servers, with no firewall rules. D/7 explicitly enables public endpoints with exact ACA IPv4 rules through its wider local plan policy; defaults stay disabled. No private endpoints, paid fallback, Cosmos Mongo RU account or additional experimental state. The retained `rg-ecommerce-dev` belongs to the bootstrap foundation. The D/1 **Destroy development** button removes all disposable resources, including existing LiveDocs, while retaining the group, state store and independent archive.

SQL serverless alone does not activate the free offer. Keep `AutoPause`; never change to `BillOverUsage` to work around an eligibility error. Current free allowance is 100,000 vCore-seconds and 32 GB data/backup per database monthly, subject to subscription eligibility. Service readback and actual creation are required; mock tests do not establish eligibility. A deleted free SQL slot can take up to an hour to become available again.

DocumentDB Free is a fixed dedicated cluster, **not request-based serverless**. Current limits include one Free cluster per subscription, no managed backup/restore, HA, database Entra authentication or diagnostic logging; inactivity pauses it after 60 days. Entra authentication for our **applications** is independent and remains a later iteration. Data here is disposable. Do not promise production durability or a zero total Azure bill: state/blob usage and other deployed resources retain their own costs.

The Mongo ARM create request includes `administrator.userName="d6operator"` and the supplied secret password. On 2026-10-06 Azure rejected the previous password-only body with a missing `userName` schema error for API `2026-06-01`; that body was incorrect. Microsoft's Bicep quickstart also supplies both fields. Free instant provisioning may assign credentials, so D/9 must verify the actual administrator returned by the service before configuring applications. We do not suppress credential drift with `ignore_changes`. SQL uses AzAPI because AzureRM 5.8.0 cannot express the two free-offer properties. Each resource has one Terraform owner.

## Driver harness retained for deployment verification

The .NET harness pins MongoDB.Driver 3.7.1, EF Core SQL Server 10.0.1 and Dapper 2.1.66, with a committed NuGet lockfile. It compiles byte-identical Users/Invoice readiness checks and settings from their D/5 commits; `contracts.json` records source paths and hashes. A minimal Users context adapter supplies only the real Mongo client to the unchanged policy. The harness checks:

- The actual `hello` policy: replica-set name, writable primary and logical-session field, followed by ping. Ping alone does not pass this gate.
- Unique indexes, standard BSON UUIDs, three-collection transaction commit, rollback after a duplicate history write, and one-winner concurrency with one history entry.
- SQL EF transaction commit/rollback, Dapper readback, unique constraints and EF optimistic concurrency. It creates and drops only a uniquely named temporary schema/table in `products-gate`; it never drops a supplied SQL database.

The Python runner checks out Payments commit `9663df14cb10886a32fa7850d1ca51537a3da009`, verifies clean tracked source, uses its frozen uv lockfile on Python 3.14 with PyMongo 4.18.1, and **calls 15 actual integration-test cases directly** against the supplied backend. These include history rollback, concurrent updates/creates, versionless-document migration, webhook atomicity/recovery, lease fencing, retry/manual resume, crash recovery and fulfillment replay. Every case uses a uniquely named database and requires successful cleanup. It does not discover pytest fixtures, which would start a local MongoDB testcontainer and test the wrong backend. Stripe, Orders and Invoice boundaries in these repository tests are existing fixtures; live end-to-end business acceptance remains D/17.

PR CI runs a native MongoDB 8 replica set and SQL Server 2022 Developer positive control using recorded Linux/amd64 image digests. CI is credential-free. **A passing native baseline proves the harness runs, not that DocumentDB is compatible.** Redacted reports contain check names and booleans, no connection strings/passwords/subscription IDs. Both suites use `azure-candidate` explicitly for Azure; native results cannot be relabelled as cloud acceptance.

The report checker requires all 16 .NET checks and all 15 Payments cases plus their cleanup and source/endpoint check (31 Payments results). It verifies the pinned driver versions and Payments source commit. Missing checks, a wrong source/driver, or a success flag paired with a failed check cannot produce a passing summary. Failed suites show every omitted check as `FAIL`; arbitrary check labels are rejected before publication.

## Optional GitHub provisioning

1. In your authenticated PowerShell terminal, select the existing development subscription. Register `Microsoft.Sql` and `Microsoft.DocumentDB` if needed (foundation/operator responsibility; the application provider deliberately does not auto-register):

   ```powershell
   az login
   az account set --subscription '<your development subscription ID>'
   az provider register --namespace Microsoft.Sql --wait
   az provider register --namespace Microsoft.DocumentDB --wait
   ```

2. In Infrastructure **Settings → Environments → development**, keep the existing D/2 Azure/state settings. Add these **individually**, not as a JSON object:

   | Type | Name | Value |
   | --- | --- | --- |
   | Variable | `DATABASE_CANDIDATE_ENABLED` | `true` |
   | Variable | `DATABASE_CANDIDATE_SQL_LOCATION` | SQL-only region after checking subscription availability, e.g. `francecentral` (availability/admission still requires verification); absent means `northeurope` |
   | Variable | `DATABASE_CANDIDATE_SUFFIX` | Your unique 6–16 lowercase letters/digits, e.g. `mike2026d6` |
   | Secret | `DATABASE_CANDIDATE_SQL_PASSWORD` | A strong unique 16–128-character password |
   | Secret | `DATABASE_CANDIDATE_MONGO_PASSWORD` | Another strong unique 16–128-character password |

   Keep `LIVEDOCS_ENABLED` equal to its existing deployment setting. Existing LiveDocs resources must remain no-op. The D/4 deployment workflow is blocked while the D/6 candidate is enabled. The candidate workflow never modifies LiveDocs; drift causes policy rejection. Do not remove the candidate flag/secrets before teardown.

   **SQL regional restrictions:** on 2026-10-06 this subscription returned `ProvisioningDisabled` in North Europe and `RequestDisallowedByAzure` in West Europe (new-customer region admission restriction), even though West Europe advertised the SQL SKU as available. The Mongo cluster was created in North Europe; retain it during SQL-only retries. Re-registering providers or changing passwords will not resolve this restriction. Check another region before setting `DATABASE_CANDIDATE_SQL_LOCATION`:

   ```powershell
   az sql db list-editions --location francecentral --service-objective GP_S_Gen5_2 --available --output table
   ```

   This reports subscription SKU availability; it does not guarantee successful server creation or eligibility for the Free offer. If no available result is returned, check another region or request the SQL regional exception through Azure support. Microsoft requires all SQL Free databases in a subscription to use the same region, so check any existing Free databases before the first successful creation here. Mongo Free and the shared LiveDocs environment stay in North Europe; do not change the root `location` to work around the SQL restriction.

   Before changing region after a failed apply, inspect the failed SQL resource and recorded Terraform state. A region change can require replacement; the candidate policy rejects delete/recreate. Clean up any recorded partial candidate using the existing teardown workflow while keeping its old region and secrets configured, then change the SQL region and plan again. **Destroy development removes existing LiveDocs too.** A failed resource outside state requires explicit cleanup/import review; do not delete the retained resource group or use a new suffix to abandon it.

3. In **Actions → Provision free database candidate**, select `main` and run **plan**, then **apply**. The apply run creates a fresh saved plan, validates Free settings/disabled public access and applies that exact file with remote-state locking. Raw plans and errors are kept in temporary private runner files and removed, rather than published in public logs. A failed apply may leave resources in state: use the existing destroy button. If creation/eligibility fails, stop and diagnose privately; do not substitute a paid service.

4. After apply, the workflow reads the three resources through Azure's management API and verifies SQL Free/AutoPause, DocumentDB Free, region and disabled public access. This uses the existing GitHub OIDC login. No workstation IP, local SDK, connection string or driver probe is required. Record the successful plan/apply workflow URLs, then continue with D/7.

   Planning and apply failures report Terraform's source location and an allowlisted category, candidate input/resource name or known Azure error code. Documented SQL creation categories and known Azure error codes are extracted from both summary and detail, including `RequestDisallowedByAzure` and `RegionDoesNotAllowProvisioning`. Raw summaries, passwords, diagnostic detail, snippets and raw plans are never printed. An unknown code can still require private Activity Log inspection; do not infer eligibility from a generic diagnostic. A failed plan does not run apply; use its safe diagnostic to investigate before retrying. Destroy is for resources already recorded by a prior apply.

   Development uses standard Terraform/provider schema validation with AzAPI's optional ARM preflight disabled. AzAPI 2.13.0 substitutes generated parent IDs when a parent server is unknown during planning; our SQL server is created in the same deployment. With optional preflight disabled, the live plan completed on 2026-10-06. The subsequent apply exposed the independent SQL regional restriction and Mongo create-body error above; the earlier filtered plan log did not establish its cause. Disabling preflight is not proof of eligibility. The saved-plan Free/scope policy remains mandatory; Azure validates the real creation request during apply, and automatic ARM readback must pass before D/6 is complete.

   References: [SQL server create/update error codes](https://learn.microsoft.com/en-us/rest/api/sql/servers/create-or-update?view=rest-sql-2023-08-01), [West Europe region admission policy](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-region-access-policy), [Azure deployment error codes](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/common-deployment-errors), [pinned provider preflight code](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/services/azapi_resource.go), [placeholder generation](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/services/preflight/preflight.go), [Microsoft preflight documentation](https://learn.microsoft.com/en-us/azure/developer/terraform/how-to-use-azapi-preflight-validation).

   If you previously applied the older operator-IP version, the new plan will reject removal of its firewall resources under the existing no-delete policy. Use **Destroy development** first and then apply the simplified version. Destroy also removes LiveDocs; the retained state foundation and independent archive survive. Keep the candidate flag and passwords configured while the candidate exists, including for teardown. An apply or readback failure leaves D/6 pending; inspect privately or use destroy for recorded partial resources.

## Acceptance and remaining work

D/6 is complete when a real apply succeeds and the existing Azure readback
checker confirms Free settings and disabled public access, whether invoked
locally or through the optional workflow. Record the safe local summary and
commit/action counts, or workflow URLs. Provisioning does not prove Mongo
compatibility and `database_candidate.selected` remains false. Native CI is
harness evidence only. The operator-reported teardown does not replace D/19's
full lifecycle proof.

- **D/7:** configure SQL/Mongo access from the existing ACA environment, with no private endpoints or paid egress gateway. Changing the disabled public-access setting requires that reviewed network change.
- **D/8:** reuse these state-owned resources when adding databases, Blob Storage and Key Vault; do not create duplicate candidates or declare them accepted prematurely.
- **D/9:** wire a bounded Azure-side verification step using the retained .NET/Payments suites, actual pinned drivers and unchanged readiness contracts. Do this before accepting the backend and business rollout. A failure requires an explicit tested alternative and revised cost estimate; never weaken `setName`/session checks or silently upgrade the tier.
- **D/17:** prove the complete cloud business flow.
- **D/19:** prove apply/destroy/reapply, empty state and cleanup after partial failure. D/6 does not require an early destructive rehearsal.

Sources checked 2026-10-06: [Mongo Bicep create request](https://learn.microsoft.com/en-us/azure/documentdb/quickstart-bicep), [SQL subscription SKU availability](https://learn.microsoft.com/en-us/cli/azure/sql/db#az-sql-db-list-editions), [SQL free offer](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer?view=azuresql), [SQL free FAQ](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer-faq?view=azuresql), [DocumentDB Free](https://learn.microsoft.com/en-us/azure/documentdb/free-tier), [DocumentDB transactions](https://learn.microsoft.com/en-us/azure/documentdb/how-to-transactions), [SQL ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases), [Mongo cluster ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2026-06-01/mongoclusters), [AzureRM 5.8.0 Mongo resource](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/internal/services/mongocluster/mongo_cluster_resource.go).
