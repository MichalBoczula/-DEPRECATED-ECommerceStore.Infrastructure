# D/7: local Container Apps database access

D/7 and the plan-checker fixes in PRs #12–#14 are merged. On 2026-10-06
the operator reported stage-one deployment working and its teardown complete.
Egress observation, Free database readback and allowed/denied data-plane access
remain pending; stage-one success does not establish application compatibility.

Use VS Code PowerShell, Terraform **1.16.5**, Azure CLI and Python 3. GitHub CI
checks code; it does not provision this stage. Keep the existing remote state:
container `development-state`, key `ecommerce/development.tfstate`, default
workspace. Run one lifecycle operation at a time, including GitHub workflows.

## Access design

The shared Consumption environment stays in North Europe; SQL uses the observed
successful region France Central and DocumentDB stays in North Europe. SQL
service-endpoint rules cannot connect this North Europe subnet to France Central
SQL. SQL and Mongo therefore use authenticated TLS public endpoints restricted
to exact ACA outbound IPv4 addresses. No workstation rule or broad Azure-services
rule is created. Free SQL/AutoPause and Mongo Free settings remain enforced.

`enable_shared_environment` enables the existing environment independently of
LiveDocs without moving its Terraform addresses. The subnet adds Storage and
Key Vault service endpoints. [D/8](development-data-services.md) supplies service-side ACLs; D/9 grants
runtime identity roles. These endpoints alone grant no data access.

Container Apps GET reports `properties.outboundIpAddresses`; Managed Environments
GET does not. Stage one reuses the pinned LiveDocs app to obtain this readback.
Its inbound IP is never used. D/9 must discover the union of the business apps'
reported egress and confirm each app's observed source before accepting access.
Discovery and Terraform accept at most 256 individual addresses, matching the
SQL server firewall-rule ceiling. This is a project bound, not a documented
DocumentDB quota; Azure apply and complete firewall readback remain required.
Larger sets fail without truncation or replacement by ranges.
Reported addresses can change; this design requires rediscovery after recreation
or connectivity failures. Custom VNet managed networking and cross-region traffic
can incur costs. No NAT, private endpoint, gateway or extra probe app is added.

## Stage one: shared environment and LiveDocs

Start from the cleared disposable state with the reviewed checkout. Sign in and
select the development subscription. Register `Microsoft.App`, `Microsoft.Network`,
`Microsoft.Sql` and `Microsoft.DocumentDB` if not already registered. The retained
resource group and remote state store must already exist.

The separate persistent LiveDocs archive foundation must also exist. Read its
`archive_storage_account` output from its independently initialized state and
set the account below. If absent, complete the existing
[one-time archive setup](livedocs-deployment.md#one-time-persistent-archive-setup)
first. This D/7 script only checks that archive; it never applies its foundation.

```powershell
az login
az account set --subscription '<your development subscription ID>'
if ($LASTEXITCODE -ne 0) { throw 'Subscription selection failed' }
$env:TFSTATE_RESOURCE_GROUP = 'rg-ecommerce-terraform-state'
$env:TFSTATE_STORAGE_ACCOUNT = 'stecomtfc3229fd85c06d3'
$env:TFSTATE_CONTAINER = 'development-state'
$env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT = '<existing archive account from foundation output>'
$env:TF_VAR_location = 'northeurope'
$env:TF_VAR_name_prefix = 'ecommerce'
$env:TF_VAR_enable_shared_environment = 'true'
$env:TF_VAR_enable_livedocs = 'true'
$env:TF_VAR_enable_database_candidate = 'false'
$env:TF_VAR_enable_database_access = 'false'
.\scripts\deploy-development-network.ps1 -Action plan
```

From an empty application state, expect **4 creates, 0 updates, 0 deletes**:
VNet, delegated subnet, shared Consumption environment and pinned LiveDocs.
Then run:

```powershell
.\scripts\deploy-development-network.ps1 -Action apply
```

Every invocation initializes the existing remote backend using Azure CLI,
creates a fresh locked plan, validates its complete scope, and discards private
plan files afterwards. Apply executes only that validated plan. LiveDocs HTTPS
routes/assets/source identity and archive existence are checked after apply.
No automatic apply follows the separate plan command. Readback failures leave
recorded resources in state for investigation or complete-state teardown.

AzureRM represents disabled log forwarding as `logs_destination = ""`; mock
plans may use `null`. Both are accepted when no Log Analytics workspace is
configured. If verification fails, the checker prints repository filenames and
line numbers without private plan values. Share those diagnostic lines for
investigation; do not share the full plan JSON or bypass the checker.

Saved-plan input variables preserve `TF_VAR_*` boolean settings as strings even
though Terraform evaluates them as booleans. The checker accepts actual booleans
and the exact strings `"true"` / `"false"`; the local script explicitly compares
the validated LiveDocs flag instead of treating the string `"false"` as truthy.

## Stage two: discover egress and restrict databases

In the same terminal (the lifecycle script sets `ARM_SUBSCRIPTION_ID`):

```powershell
python scripts/discover-aca-egress.py --subscription $env:ARM_SUBSCRIPTION_ID `
  --app ca-ecommerce-dev-livedocs `
  --output environments/development/aca-egress.auto.tfvars.json
if ($LASTEXITCODE -ne 0) { throw 'Egress discovery failed; leave database access disabled' }
```

Discovery is read-only. It requires a successfully provisioned Consumption app
in `cae-ecommerce-dev` and a nonempty canonical public IPv4 list. Only those
addresses are written to the ignored local file; no connection strings or
passwords are stored there. It fails rather than substituting inbound addresses.

Enable the Free candidates and explicit access:

```powershell
$env:TF_VAR_enable_database_candidate = 'true'
$env:TF_VAR_candidate_suffix = 'mike2026'
$env:TF_VAR_candidate_sql_location = 'francecentral'
$env:TF_VAR_candidate_sql_password = [pscredential]::new('unused', (Read-Host 'SQL password (16–128 characters)' -AsSecureString)).GetNetworkCredential().Password
$env:TF_VAR_candidate_mongo_password = [pscredential]::new('unused', (Read-Host 'Mongo password (16–128 characters)' -AsSecureString)).GetNetworkCredential().Password
$env:TF_VAR_enable_database_access = 'true'
.\scripts\deploy-development-network.ps1 -Action plan
```

For **N discovered IPs**, expect **3 + 2N creates**, with the four stage-one
resources unchanged: three database resources and one SQL/Mongo firewall rule
per IP. A different count needs review. Eligibility and region admission still
require actual creation. The policy rejects paid fallback, database/network/app
deletes or replacements, unrecognized resources and broad firewall ranges.

```powershell
.\scripts\deploy-development-network.ps1 -Action apply
```

Before applying an access-enabled plan, the script re-reads LiveDocs' reported
egress and rejects a stale IP list. After apply it checks the Free database
properties, public endpoint settings, current reported egress and the complete
SQL/Mongo firewall lists. Unexpected extra rules, including `0.0.0.0`, fail
readback. This is management-plane evidence; it does not prove an authenticated
database connection. D/9 retains the actual application driver/transaction gates.

## Live evidence and refreshing addresses

After LiveDocs has passed HTTPS checks, a bounded Azure-side source observation
can use its existing BusyBox `wget` (no database credentials):

```powershell
az containerapp exec --resource-group rg-ecommerce-dev --name ca-ecommerce-dev-livedocs `
  --command 'wget -q -T 10 -O - https://api.ipify.org'
```

The public IP service receives only the egress request. Record the observed IP
and verify it belongs to the discovered set. Stop and investigate a mismatch;
do not open broad access. This observation proves a source address, not SQL or
Mongo connectivity. D/7 live acceptance still needs bounded allowed ACA access
and denial from an unlisted source. D/9 performs authenticated checks from the
actual pinned business containers, including readiness and transactions.
Allow for Mongo firewall propagation (documented as up to 15 minutes); do not
use a passing ping or management GET as driver compatibility evidence.

After an egress change, rerun discovery and local plan/apply with the same
candidate inputs. The policy permits deletion only of obsolete Terraform-owned
firewall rules and requires the final rules to equal the new address set. It
still rejects replacements or database deletion. Do not remove working firewall
inputs, change passwords or change database regions to hide a failure.

## Stop the development session

Use the [complete-state saved-plan teardown](local-development.md#destroy-the-current-disposable-environment).
Keep all current flags, suffix, regions, passwords and the local IP file until
cleanup succeeds. This destroys databases, firewalls, LiveDocs and networking;
it retains the bootstrap group/state and independent archive. Verify the
archive account still exists. D/19 audits managed groups, backups, soft deletes
and residual billing; an empty application state is not a zero-cost proof.

After verified cleanup, remove the ignored egress file and password variables.
Do not use the D/6 or D/4 GitHub deployment workflow to manage this expanded
D/7 scope. Pushes and PRs never deploy it.

Primary references checked 2026-10-06:

- [SQL service-endpoint regional limits](https://learn.microsoft.com/en-us/azure/azure-sql/database/vnet-service-endpoint-rule-overview?view=azuresql)
- [Container Apps GET and outboundIpAddresses](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps/get?view=rest-resource-manager-containerapps-2026-01-01)
- [Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [DocumentDB firewall rules and propagation](https://learn.microsoft.com/en-us/azure/documentdb/how-to-configure-firewall)

## ACA delete polling recovery

The operator observed `polling support for the Content-Type "" was not
implemented` after both ACA app and environment deletes. Azure removed the
resources even though the pinned AzureRM SDK reported a polling failure. The
SDK's LRO parser lacked handling for a successful empty HTTP 204 response;
[upstream fix #1367](https://github.com/hashicorp/go-azure-sdk/pull/1367) was
merged on 2026-10-05. The pinned provider is unchanged in this task.

Verify that the resource is actually absent, then rerun the complete-state
destroy with the same inputs. Terraform refresh reconciles already-deleted
resources and continues remaining deletes such as the VNet. Do not remove
resources from state or force-unlock an active operation. This failure is not
a reason to create replacement infrastructure or increase polling timeouts.

The address ceiling follows the [Azure SQL firewall limits](https://learn.microsoft.com/en-us/azure/azure-sql/database/firewall-configure?view=azuresql).
