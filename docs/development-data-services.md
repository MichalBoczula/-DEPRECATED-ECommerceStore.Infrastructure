# D/8: local business data infrastructure

D/8 adds a disposable business storage account, private `invoices` and `photos`
containers, and a Standard Key Vault to the existing development state. It reuses
D/6's Free SQL database (`products-gate`) and Mongo cluster. The persistent
LiveDocs archive stays in its separate root and survives application teardown.

This is infrastructure provisioning. D/9 adds business apps, managed identities,
scoped data roles, Key Vault references and actual driver connectivity tests.
D/10 creates Mongo collections/indexes and seeds data. D/12 implements the Blob
adapters; the existing Invoice file adapter is not changed by this task.

## Plan and apply from VS Code PowerShell

After merging this change, pull `main`. Use Terraform **1.16.5**, Azure CLI and
Python 3 on PATH. Keep the existing development subscription, independent remote
backend and persistent archive foundation. If the archive is absent, follow
[its one-time setup](livedocs-deployment.md#one-time-persistent-archive-setup).
Run only one lifecycle operation at a time.

```powershell
git pull --ff-only
az login
az account set --subscription '0251d4d6-02b8-4b3f-a390-a9f914cfebea'
if ($LASTEXITCODE -ne 0) { throw 'Subscription selection failed' }
$env:TFSTATE_RESOURCE_GROUP = 'rg-ecommerce-terraform-state'
$env:TFSTATE_STORAGE_ACCOUNT = 'stecomtfc3229fd85c06d3'
$env:TFSTATE_CONTAINER = 'development-state'
$archiveAccounts = @(az storage account list --resource-group rg-ecommerce-livedocs-archive --query "[?tags.lifecycle=='persistent-archive'].name" --output tsv)
if ($LASTEXITCODE -ne 0 -or $archiveAccounts.Count -ne 1) { throw 'Expected the existing persistent archive account' }
$env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT = $archiveAccounts[0].Trim()
```

Register `Microsoft.Storage` and `Microsoft.KeyVault` once if not registered,
alongside the existing App/Network/Sql/DocumentDB namespaces. The local account
needs management rights in the retained development group and access to the
existing state backend. Key Vault purge at teardown needs deleted-vault purge
permission, which is outside the live vault's resource scope. CI identities
are not granted new subscription permissions by this change.

```powershell
$env:TF_VAR_location = 'northeurope'
$env:TF_VAR_name_prefix = 'ecommerce'
$env:TF_VAR_enable_shared_environment = 'true'
$env:TF_VAR_enable_livedocs = 'true'
$env:TF_VAR_enable_data_services = 'true'
$env:TF_VAR_enable_database_candidate = 'true'
$env:TF_VAR_candidate_suffix = 'mike2026'
$env:TF_VAR_candidate_sql_location = 'francecentral'
$env:TF_VAR_enable_database_access = 'false'
$env:TF_VAR_candidate_sql_password = [pscredential]::new('unused', (Read-Host 'SQL password (16–128 characters)' -AsSecureString)).GetNetworkCredential().Password
$env:TF_VAR_candidate_mongo_password = [pscredential]::new('unused', (Read-Host 'Mongo password (16–128 characters)' -AsSecureString)).GetNetworkCredential().Password
.\scripts\deploy-development-network.ps1 -Action plan
```

From the cleared disposable state, expect **11 creates, 0 updates, 0 deletes**:
four network/LiveDocs resources, three database resources, and four D/8
resources. There are no database firewall rules yet. If resources already exist,
expect fewer creates and investigate any credential updates before applying.
The checker rejects paid database fallback, broad ACLs and resource replacements.
AzureRM may show Storage `ip_rules = (known after apply)` even when the source
sets `ip_rules = []`. On first creation the checker accepts this only when the
saved configuration proves the empty literal and the plan marks it unknown.
Known nonempty IP rules and unresolved rules on existing resources are rejected;
post-apply ARM readback still requires an actually empty list.

```powershell
.\scripts\deploy-development-network.ps1 -Action apply
terraform '-chdir=environments/development' output -json data_services
```

Apply generates and checks a fresh saved plan. It checks storage/vault ACLs,
private containers, Free database properties with public database access off,
LiveDocs HTTPS/source identity and archive survival. Output contains resource
identifiers and naming contracts, never secret values. ARM readback does not
prove application data-plane access. A failed readback leaves state available
for diagnosis or teardown; it does not fall back to wider access.

Storage and Key Vault expose authenticated public endpoints with network ACLs
restricted to the existing ACA subnet's service endpoints: default deny, no
IP rules, no trusted-services bypass. Blob public access and shared keys are
disabled. Entra roles are still required; subnet access alone grants no rights.
Terraform manages containers through ARM, avoiding a workstation Blob firewall
rule. No new private endpoint, NAT gateway or probe app is added.

## Database access and logical database names

After recreation, rediscover egress using the
[D/7 stage-two procedure](development-network-access.md#stage-two-discover-egress-and-restrict-databases).
Keep the same passwords and database names. Enable database access and plan
again: with databases already present, expect **2N firewall creates** for N
reported IPs, plus endpoint updates on the existing SQL server/Mongo cluster.
Do not reuse an egress file from a destroyed environment without fresh discovery.
D/7 source observation and allowed/denied tests remain required; D/9 checks the
actual SQL/Mongo application drivers and transactions from the business apps.

The output records the existing application names:

| Service | Database |
| --- | --- |
| Products | SQL `products-gate` |
| Users | Mongo `ecommerce-store-users-db` |
| Invoice | Mongo `ecommerce-store-invoice-db` |
| Payments | Mongo `ecommerce_store_payments` |

Mongo logical databases appear when their collections/indexes/data are created.
Terraform provisions one Free cluster and records these names; it does not
pretend ARM creates three database resources. D/9/D/10 complete initialization.

## Put runtime secrets into the business vault

Use the hidden terminal prompt, with the current Azure login and initialized
remote state. No value goes in command history, arguments, Terraform resources
or outputs. The setter verifies the vault belongs to this subscription and
`rg-ecommerce-dev`, writes through ARM `vaults/secrets/write`, and deletes its
private temporary request file even on failure. That management permission is
required; Key Vault data-reader roles alone do not authorize this operation.
Avoid shell transcripts or debug logging while entering values.

```powershell
python scripts/set-development-secret.py --name products-sql-connection
python scripts/set-development-secret.py --name users-mongo-connection
python scripts/set-development-secret.py --name invoice-mongo-connection
python scripts/set-development-secret.py --name payments-mongo-connection
```

Enter each service's intended connection string using the newly provisioned
endpoints and its database name. D/9 verifies the real driver options before
runtime wiring; this setter only stores values. The two reserved Stripe names
`stripe-secret-key` and `stripe-webhook-secret` are for **test mode** D/13 wiring.
No Stripe provisioning or application binding is performed here.

Database administrator passwords remain in Terraform state and saved plans,
even when marked sensitive. Keep backend access restricted and preserve current
inputs until teardown. Runtime secret values supplied through the setter are
outside Terraform state. D/9 will grant only the relevant runtime identities
Key Vault secret reads and per-container Blob data roles; no roles are added now.

## Destroy

Use the existing [complete-state local teardown](local-development.md#destroy-the-current-disposable-environment)
with all current inputs retained. It removes business storage/data, vault,
databases, firewall rules, LiveDocs and network; the independent state store
and persistent archive survive. Business files are synthetic and disposable:
no Blob versions/soft-delete retention is configured.

Key Vault always uses soft delete. This root explicitly purges its disposable
vault on destroy and disables automatic recovery of a previously deleted vault.
Purge protection is off and the retention minimum is seven days. If purge
permission is missing, resolve that failure before reusing the name; do not
silently recover previous secrets. D/19 audits deleted vaults, managed groups,
backups and residual billing. Empty Terraform state alone does not prove purge
or zero residual cost.

For the known ACA delete polling error, see
[the recovery note](development-network-access.md#aca-delete-polling-recovery).

Primary references checked 2026-10-06:

- [Key Vault virtual network service endpoints](https://learn.microsoft.com/en-us/azure/key-vault/general/network-security)
- [ARM Key Vault secrets resource](https://learn.microsoft.com/en-us/azure/templates/microsoft.keyvault/2023-07-01/vaults/secrets)
- [Key Vault soft delete and purge](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview)
- [Storage service endpoints](https://learn.microsoft.com/en-us/azure/storage/common/storage-network-security-virtual-networks)
