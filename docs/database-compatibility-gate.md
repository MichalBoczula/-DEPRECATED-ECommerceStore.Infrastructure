# D/6: provision the free database candidate

Status: implementation prepared; **live Azure provisioning pending**. D/6 provisions a provisional backend and verifies its Free settings. D/7 configures access from Container Apps; D/9 verifies real driver compatibility before accepting the backend for the applications. D/17 covers business flows and D/19 covers destroy/recreate proof. The D/5 application release remains unchanged.

## Candidate and cost boundary

| Candidate | Explicit configuration | Acceptance requirement |
| --- | --- | --- |
| Azure SQL Database | North Europe, General Purpose serverless, `useFreeLimit=true`, `freeLimitExhaustionBehavior=AutoPause`, 32 GiB limit, local backup redundancy | The subscription can create the free offer; ARM readback confirms the free settings (D/6); EF Core SQL Server 10.0.1 and Dapper 2.1.66 checks pass from Azure (D/9) |
| Azure DocumentDB Free | North Europe, `Free`, 32 GiB, one shard, HA disabled, Mongo compatibility 8.0, NativeAuth | Terraform creation and Free readback (D/6); unchanged readiness and driver checks from Azure (D/9); recreation proof (D/19) |

Both are **experiments in the existing disposable development state**, container `development-state`, key `ecommerce/development.tfstate`, default workspace. Three managed resources: SQL logical server, SQL database and Mongo cluster. Public data-plane access is disabled on both servers, with no firewall rules. D/7 will configure the affordable ACA access path; the candidate is intentionally unreachable by applications until then. No private endpoints, paid fallback, Cosmos Mongo RU account or additional experimental state. The retained `rg-ecommerce-dev` belongs to the bootstrap foundation. The D/1 **Destroy development** button removes all disposable resources, including existing LiveDocs, while retaining the group, state store and independent archive.

SQL serverless alone does not activate the free offer. Keep `AutoPause`; never change to `BillOverUsage` to work around an eligibility error. Current free allowance is 100,000 vCore-seconds and 32 GB data/backup per database monthly, subject to subscription eligibility. Service readback and actual creation are required; mock tests do not establish eligibility. A deleted free SQL slot can take up to an hour to become available again.

DocumentDB Free is a fixed dedicated cluster, **not request-based serverless**. Current limits include one Free cluster per subscription, no managed backup/restore, HA, database Entra authentication or diagnostic logging; inactivity pauses it after 60 days. Entra authentication for our **applications** is independent and remains a later iteration. Data here is disposable. Do not promise production durability or a zero total Azure bill: state/blob usage and other deployed resources retain their own costs.

Instant Free provisioning now assigns the administrator name. The cluster uses AzAPI with the password and no invented `userName`; D/9 runtime configuration must read the assigned name. AzureRM 5.8.0 supports `Free` but requires a user-specified NativeAuth administrator name. We avoid hiding a mismatch with `ignore_changes`. If the service rejects the password-only creation contract, record the failure and revise the candidate explicitly; never upgrade the SKU to make creation succeed. SQL also uses AzAPI because AzureRM 5.8.0 cannot express the two free-offer properties. Each resource has one Terraform owner.

## Driver harness retained for deployment verification

The .NET harness pins MongoDB.Driver 3.7.1, EF Core SQL Server 10.0.1 and Dapper 2.1.66, with a committed NuGet lockfile. It compiles byte-identical Users/Invoice readiness checks and settings from their D/5 commits; `contracts.json` records source paths and hashes. A minimal Users context adapter supplies only the real Mongo client to the unchanged policy. The harness checks:

- The actual `hello` policy: replica-set name, writable primary and logical-session field, followed by ping. Ping alone does not pass this gate.
- Unique indexes, standard BSON UUIDs, three-collection transaction commit, rollback after a duplicate history write, and one-winner concurrency with one history entry.
- SQL EF transaction commit/rollback, Dapper readback, unique constraints and EF optimistic concurrency. It creates and drops only a uniquely named temporary schema/table in `products-gate`; it never drops a supplied SQL database.

The Python runner checks out Payments commit `9663df14cb10886a32fa7850d1ca51537a3da009`, verifies clean tracked source, uses its frozen uv lockfile on Python 3.14 with PyMongo 4.18.1, and **calls 15 actual integration-test cases directly** against the supplied backend. These include history rollback, concurrent updates/creates, versionless-document migration, webhook atomicity/recovery, lease fencing, retry/manual resume, crash recovery and fulfillment replay. Every case uses a uniquely named database and requires successful cleanup. It does not discover pytest fixtures, which would start a local MongoDB testcontainer and test the wrong backend. Stripe, Orders and Invoice boundaries in these repository tests are existing fixtures; live end-to-end business acceptance remains D/17.

PR CI runs a native MongoDB 8 replica set and SQL Server 2022 Developer positive control using recorded Linux/amd64 image digests. CI is credential-free. **A passing native baseline proves the harness runs, not that DocumentDB is compatible.** Redacted reports contain check names and booleans, no connection strings/passwords/subscription IDs. Both suites use `azure-candidate` explicitly for Azure; native results cannot be relabelled as cloud acceptance.

The report checker requires all 16 .NET checks and all 15 Payments cases plus their cleanup and source/endpoint check (31 Payments results). It verifies the pinned driver versions and Payments source commit. Missing checks, a wrong source/driver, or a success flag paired with a failed check cannot produce a passing summary. Failed suites show every omitted check as `FAIL`; arbitrary check labels are rejected before publication.

## Provisioning after merging this PR

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
   | Variable | `DATABASE_CANDIDATE_SUFFIX` | Your unique 6–16 lowercase letters/digits, e.g. `mike2026d6` |
   | Secret | `DATABASE_CANDIDATE_SQL_PASSWORD` | A strong unique 16–128-character password |
   | Secret | `DATABASE_CANDIDATE_MONGO_PASSWORD` | Another strong unique 16–128-character password |

   Keep `LIVEDOCS_ENABLED` equal to its existing deployment setting. Existing LiveDocs resources must remain no-op. The D/4 deployment workflow is blocked while the D/6 candidate is enabled. The candidate workflow never modifies LiveDocs; drift causes policy rejection. Do not remove the candidate flag/secrets before teardown.

3. In **Actions → Provision free database candidate**, select `main` and run **plan**, then **apply**. The apply run creates a fresh saved plan, validates Free settings/disabled public access and applies that exact file with remote-state locking. Raw plans and errors are kept in temporary private runner files and removed, rather than published in public logs. A failed apply may leave resources in state: use the existing destroy button. If creation/eligibility fails, stop and diagnose privately; do not substitute a paid service.

4. After apply, the workflow reads the three resources through Azure's management API and verifies SQL Free/AutoPause, DocumentDB Free, region and disabled public access. This uses the existing GitHub OIDC login. No workstation IP, local SDK, connection string or driver probe is required. Record the successful plan/apply workflow URLs, then continue with D/7.

   If you previously applied the older operator-IP version, the new plan will reject removal of its firewall resources under the existing no-delete policy. Use **Destroy development** first and then apply the simplified version. Destroy also removes LiveDocs; the retained state foundation and independent archive survive. Keep the candidate flag and passwords configured while the candidate exists, including for teardown. An apply or readback failure leaves D/6 pending; inspect privately or use destroy for recorded partial resources.

## Acceptance and remaining work

D/6 is complete when a real apply succeeds and automatic Azure readback confirms the Free settings and disabled public access. Provisioning does not prove Mongo compatibility and `database_candidate.selected` remains false. Native CI is harness evidence only.

- **D/7:** configure SQL/Mongo access from the existing ACA environment, with no private endpoints or paid egress gateway. Changing the disabled public-access setting requires that reviewed network change.
- **D/8:** reuse these state-owned resources when adding databases, Blob Storage and Key Vault; do not create duplicate candidates or declare them accepted prematurely.
- **D/9:** wire a bounded Azure-side verification step using the retained .NET/Payments suites, actual pinned drivers and unchanged readiness contracts. Do this before accepting the backend and business rollout. A failure requires an explicit tested alternative and revised cost estimate; never weaken `setName`/session checks or silently upgrade the tier.
- **D/17:** prove the complete cloud business flow.
- **D/19:** prove apply/destroy/reapply, empty state and cleanup after partial failure. D/6 does not require an early destructive rehearsal.

Sources checked 2026-10-05: [SQL free offer](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer?view=azuresql), [SQL free FAQ](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer-faq?view=azuresql), [DocumentDB Free](https://learn.microsoft.com/en-us/azure/documentdb/free-tier), [DocumentDB transactions](https://learn.microsoft.com/en-us/azure/documentdb/how-to-transactions), [SQL ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases), [Mongo cluster ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2026-06-01/mongoclusters), [AzureRM 5.8.0 Mongo resource](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/internal/services/mongocluster/mongo_cluster_resource.go).
