# D/6: free database candidate and compatibility gate

Status: implementation prepared; **Azure acceptance pending**. This gate does not select a database for the application. D/8 consumes only a backend that passed the live evidence below. The D/5 application release remains unchanged.

## Candidate and cost boundary

| Candidate | Explicit configuration | Acceptance requirement |
| --- | --- | --- |
| Azure SQL Database | North Europe, General Purpose serverless, `useFreeLimit=true`, `freeLimitExhaustionBehavior=AutoPause`, 32 GiB limit, local backup redundancy | The subscription can create the free offer; ARM readback confirms the free settings; EF Core SQL Server 10.0.1 and Dapper 2.1.66 checks pass |
| Azure DocumentDB Free | North Europe, `Free`, 32 GiB, one shard, HA disabled, Mongo compatibility 8.0, NativeAuth | Terraform creation, assigned administrator, unchanged readiness, transaction/index/concurrency/replay checks and recreation all pass |

Both are **experiments in the existing disposable development state**, container `development-state`, key `ecommerce/development.tfstate`, default workspace. Five managed resources: SQL logical server, SQL database, Mongo cluster and one exact operator-IP firewall rule per server. No private endpoints, paid fallback, Cosmos Mongo RU account or additional experimental state. The retained `rg-ecommerce-dev` belongs to the bootstrap foundation. The D/1 **Destroy development** button removes all disposable resources, including existing LiveDocs, while retaining the group, state store and independent archive.

SQL serverless alone does not activate the free offer. Keep `AutoPause`; never change to `BillOverUsage` to work around an eligibility error. Current free allowance is 100,000 vCore-seconds and 32 GB data/backup per database monthly, subject to subscription eligibility. Service readback and actual creation are required; mock tests do not establish eligibility. A deleted free SQL slot can take up to an hour to become available again.

DocumentDB Free is a fixed dedicated cluster, **not request-based serverless**. Current limits include one Free cluster per subscription, no managed backup/restore, HA, database Entra authentication or diagnostic logging; inactivity pauses it after 60 days. Entra authentication for our **applications** is independent and remains a later iteration. Data here is disposable. Do not promise production durability or a zero total Azure bill: state/blob usage and other deployed resources retain their own costs.

Instant Free provisioning now assigns the administrator name. The cluster uses AzAPI with the password and no invented `userName`; the live probe reads the assigned name. AzureRM 5.8.0 supports `Free` but requires a user-specified NativeAuth administrator name. We avoid hiding a mismatch with `ignore_changes`. If the service rejects the password-only creation contract, record the failure and revise the candidate explicitly; never upgrade the SKU to make creation succeed. SQL also uses AzAPI because AzureRM 5.8.0 cannot express the two free-offer properties. Each resource has one Terraform owner.

## What is tested

The .NET harness pins MongoDB.Driver 3.7.1, EF Core SQL Server 10.0.1 and Dapper 2.1.66, with a committed NuGet lockfile. It compiles byte-identical Users/Invoice readiness checks and settings from their D/5 commits; `contracts.json` records source paths and hashes. A minimal Users context adapter supplies only the real Mongo client to the unchanged policy. The harness checks:

- The actual `hello` policy: replica-set name, writable primary and logical-session field, followed by ping. Ping alone does not pass this gate.
- Unique indexes, standard BSON UUIDs, three-collection transaction commit, rollback after a duplicate history write, and one-winner concurrency with one history entry.
- SQL EF transaction commit/rollback, Dapper readback, unique constraints and EF optimistic concurrency. It creates and drops only a uniquely named temporary schema/table in `products-gate`; it never drops a supplied SQL database.

The Python runner checks out Payments commit `9663df14cb10886a32fa7850d1ca51537a3da009`, verifies clean tracked source, uses its frozen uv lockfile on Python 3.14 with PyMongo 4.18.1, and **calls 15 actual integration-test cases directly** against the supplied backend. These include history rollback, concurrent updates/creates, versionless-document migration, webhook atomicity/recovery, lease fencing, retry/manual resume, crash recovery and fulfillment replay. Every case uses a uniquely named database and requires successful cleanup. It does not discover pytest fixtures, which would start a local MongoDB testcontainer and test the wrong backend. Stripe, Orders and Invoice boundaries in these repository tests are existing fixtures; live end-to-end business acceptance remains D/17.

PR CI runs a native MongoDB 8 replica set and SQL Server 2022 Developer positive control using recorded Linux/amd64 image digests. CI is credential-free. **A passing native baseline proves the harness runs, not that DocumentDB is compatible.** Redacted reports contain check names and booleans, no connection strings/passwords/subscription IDs. Both suites use `azure-candidate` explicitly for Azure; native results cannot be relabelled as cloud acceptance.

## Operator setup after merging this PR

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
   | Variable | `DATABASE_CANDIDATE_OPERATOR_IPV4` | Your workstation's current public IPv4; one address, no range/wildcard |
   | Secret | `DATABASE_CANDIDATE_SQL_PASSWORD` | A strong unique 16–128-character password |
   | Secret | `DATABASE_CANDIDATE_MONGO_PASSWORD` | Another strong unique 16–128-character password |

   Keep `LIVEDOCS_ENABLED` equal to its existing deployment setting. Existing LiveDocs resources must remain no-op. The D/4 deployment workflow is blocked while the D/6 candidate is enabled. The candidate workflow never modifies LiveDocs; drift causes policy rejection. Do not remove the candidate flag/secrets before teardown.

3. In **Actions → Provision database compatibility candidate**, select `main` and run **plan**, then **apply**. The apply run creates a fresh saved plan, validates Free settings/one-IP scope and applies that exact file with remote-state locking. Raw plans and errors are kept in temporary private runner files and removed, rather than published in public logs. A failed apply may leave resources in state: use the existing destroy button. If creation/eligibility fails, stop and diagnose privately; do not substitute a paid service.

4. Install .NET SDK 10, Python 3.14 and `uv==0.12.18` on your workstation. Pull the merged Infrastructure repository, open its root in PowerShell, and run:

   ```powershell
   python -m pip install uv==0.12.18
   .\scripts\probe-database-candidate.ps1 -Suffix mike2026d6 -Cycle first
   ```

   Replace the example suffix with the environment variable's value. The script uses your Azure CLI login, reads ARM free-offer settings and the assigned Mongo administrator/connection template, prompts for both passwords securely, installs frozen dependencies, then runs both driver suites against those endpoints with certificate validation. It writes redacted evidence under the ignored `artifacts/database-gate/first` directory. Dependency failures produce **private local logs**; do not publish them without review. There is no Docker fallback in the Azure probe. A readiness failure is real evidence; do not remove `setName` or the session checks just to turn the report green.

5. Run **Destroy development**, confirm its summary shows empty disposable state and no children in the retained group, and record the workflow URL. This also destroys LiveDocs if currently deployed. Preserve `first` redacted reports. Run candidate **apply** again with the same settings (allow up to one hour for a free SQL slot to be released if the service requires it), then:

   ```powershell
   .\scripts\probe-database-candidate.ps1 -Suffix mike2026d6 -Cycle recreated
   ```

   Record the two apply workflow URLs, destroy URL, UTC times and any quota-release delay. The recreated probe must pass independently, including service-assigned credentials. Run destroy again when finished. Only after successful teardown set `DATABASE_CANDIDATE_ENABLED=false`; remove the two candidate secrets if no longer needed. Restore/reapply LiveDocs through D/4 when desired.

## Acceptance and fallback decision

D/6 stays open until both redacted Azure driver reports pass in **both** cycles, Free readback matches, and deletion/empty-state/recreation evidence is recorded. First-pass provisioning alone is insufficient. If any check fails, record the check name, retain redacted evidence, destroy the candidate, and select/test a native Mongo alternative with a revised cost estimate before D/8. No candidate, native baseline or provider schema audit is silently recorded as an accepted backend. The application image pins and readiness policies remain unchanged.

Sources checked 2026-10-05: [SQL free offer](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer?view=azuresql), [SQL free FAQ](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer-faq?view=azuresql), [DocumentDB Free](https://learn.microsoft.com/en-us/azure/documentdb/free-tier), [DocumentDB transactions](https://learn.microsoft.com/en-us/azure/documentdb/how-to-transactions), [SQL ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.sql/2023-08-01/servers/databases), [Mongo cluster ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2026-06-01/mongoclusters), [AzureRM 5.8.0 Mongo resource](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/internal/services/mongocluster/mongo_cluster_resource.go).
