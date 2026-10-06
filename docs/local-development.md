# Local development lifecycle (VS Code / PowerShell)

Run Azure provisioning and teardown locally with Terraform; GitHub CI continues
to validate repository changes. Existing manual OIDC workflows are optional.
Local execution still creates resources in Azure and uses the same remote state.
It does not require your workstation IP or a local database driver probe.
For the shared environment and database firewalls, follow the
[D/7 two-stage runbook](development-network-access.md) and its local lifecycle script.

Use the reviewed checkout and Terraform **1.16.5**, Azure CLI and Python 3 on
PATH. Run commands from the repository root. Keep current input values until
teardown finishes. A different Mongo password causes a real password update.
Run one lifecycle operation at a time, including optional GitHub workflows;
remote locking remains enabled and must never be bypassed.

## Authenticate and initialize

If the same terminal already initialized successfully, continue at teardown.
In a new terminal, restore your Terraform 1.16.5 PATH, then:

```powershell
az login
az account set --subscription '<your development subscription ID>'
if ($LASTEXITCODE -ne 0) { throw 'Azure subscription selection failed' }
Remove-Item Env:ARM_CLIENT_ID, Env:ARM_CLIENT_SECRET -ErrorAction SilentlyContinue
$env:ARM_USE_OIDC = 'false'
$env:ARM_USE_MSI = 'false'
$env:ARM_USE_CLI = 'true'
$env:ARM_USE_AZUREAD = 'true'
$env:ARM_SUBSCRIPTION_ID = (az account show --query id --output tsv).Trim()
$env:ARM_TENANT_ID = (az account show --query tenantId --output tsv).Trim()
$env:TF_WORKSPACE = 'default'
$env:TFSTATE_RESOURCE_GROUP = 'rg-ecommerce-terraform-state'
$env:TFSTATE_STORAGE_ACCOUNT = 'stecomtfc3229fd85c06d3'
$env:TFSTATE_CONTAINER = 'development-state'
$env:TF_VAR_enable_livedocs = 'false'
$env:TF_VAR_enable_database_candidate = 'true'
$env:TF_VAR_candidate_suffix = 'mike2026'
$env:TF_VAR_location = 'northeurope'
$env:TF_VAR_candidate_sql_location = 'francecentral'
$env:TF_VAR_candidate_sql_password = [pscredential]::new('unused', (Read-Host 'Existing SQL password' -AsSecureString)).GetNetworkCredential().Password
$env:TF_VAR_candidate_mongo_password = [pscredential]::new('unused', (Read-Host 'Existing Mongo password' -AsSecureString)).GetNetworkCredential().Password

terraform "-chdir=environments/development" init -reconfigure -lockfile=readonly `
  "-backend-config=resource_group_name=$env:TFSTATE_RESOURCE_GROUP" `
  "-backend-config=storage_account_name=$env:TFSTATE_STORAGE_ACCOUNT" `
  "-backend-config=container_name=$env:TFSTATE_CONTAINER" `
  '-backend-config=key=ecommerce/development.tfstate' `
  '-backend-config=use_oidc=false' `
  '-backend-config=use_cli=true' `
  '-backend-config=use_azuread_auth=true'
if ($LASTEXITCODE -ne 0) { throw 'Terraform initialization failed' }
terraform "-chdir=environments/development" state list
if ($LASTEXITCODE -ne 0) { throw 'Terraform state read failed' }
```

These values identify this development environment. Other operators must use
their own authorized subscription/backend and existing resource inputs. Do not
select a different backend key to bypass a failure. Explicit `use_oidc=false`
overrides the root backend's GitHub OIDC default; environment variables alone
do not override that configured value. Do not run the GitHub-only Bash deploy
scripts from this terminal: they enforce runner/OIDC configuration.

## Destroy the current disposable environment

Keep the candidate enabled and its passwords available. After D/7, also retain
the shared-environment/LiveDocs/access flags and ignored egress-IP file until
teardown completes. Restore the actual deployment inputs instead of copying
the database-only flags above over an existing D/7 environment. This complete-state
destroy also removes any state-owned LiveDocs/network resources if present.
Before D/7, the database-only environment contained these three managed
addresses:

- `azurerm_mssql_server.database_candidate[0]`
- `azapi_resource.sql_candidate[0]`
- `azapi_resource.mongo_candidate[0]`

Use a private temporary directory. Binary plans and their JSON contain secrets;
never commit or upload them. Write JSON as UTF-8 without BOM for the validators,
including in Windows PowerShell 5.1.

```powershell
$localLifecycleDir = Join-Path $env:TEMP ('ecommerce-lifecycle-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $localLifecycleDir | Out-Null
$localDestroyPlan = Join-Path $localLifecycleDir 'destroy.tfplan'
$localPlanJson = Join-Path $localLifecycleDir 'plan.json'
terraform "-chdir=environments/development" plan -destroy -lock-timeout=5m "-out=$localDestroyPlan"
if ($LASTEXITCODE -ne 0) { throw 'Destroy planning failed; do not apply an old plan' }
$localPlanText = terraform "-chdir=environments/development" show -json $localDestroyPlan
if ($LASTEXITCODE -ne 0) { throw 'Plan export failed' }
[IO.File]::WriteAllText($localPlanJson, ($localPlanText -join "`n"), [Text.UTF8Encoding]::new($false))
$env:TFSTATE_RESOURCE_GROUP = 'rg-ecommerce-terraform-state'
python scripts/validate-destroy-plan.py $localPlanJson
if ($LASTEXITCODE -ne 0) { throw 'Destroy scope policy rejected the plan' }
```

For the reported three-resource environment, review **0 adds, 0 changes, 3
destroys**. Investigate a different result before applying; a data-source entry
is not an additional managed resource. The policy excludes bootstrap storage,
the retained development group itself and the persistent archive.

```powershell
terraform "-chdir=environments/development" apply -lock-timeout=5m $localDestroyPlan
if ($LASTEXITCODE -ne 0) { throw 'Destroy failed; preserve inputs and investigate partial state' }
terraform "-chdir=environments/development" state list
if ($LASTEXITCODE -ne 0) { throw 'Post-destroy state read failed' }
az resource list --subscription $env:ARM_SUBSCRIPTION_ID --resource-group rg-ecommerce-dev --query '[].{Name:name,Type:type,Location:location}' --output table
if ($LASTEXITCODE -ne 0) { throw 'Resource inventory failed' }
az group exists --subscription $env:ARM_SUBSCRIPTION_ID --name rg-ecommerce-dev --output tsv
az storage account show --subscription $env:ARM_SUBSCRIPTION_ID --resource-group rg-ecommerce-terraform-state --name stecomtfc3229fd85c06d3 --query name --output tsv
```

Acceptance: state and resource table are empty, group existence returns `true`,
and the state account name is returned. If a separate LiveDocs archive exists,
verify its account still exists in `rg-ecommerce-livedocs-archive`. D/19 adds the
full managed-group, backup, soft-delete and billing audit.

**Failed SQL creation outside state:** on 2026-10-06 a generic empty resource
list did not prove the SQL name was free; Azure still reported a North Europe
server when France Central creation was attempted. Check the known name with
`az sql server show --resource-group rg-ecommerce-dev --name sql-ecommerce-dev-d6-mike2026`.
A confirmed `ResourceNotFound` is absence; an auth/transport error is not. If a
server remains after state is empty, investigate ownership and explicitly
reconcile that orphan. Never use `state rm`, delete the retained group, or change
the suffix merely to hide it. Normal state-owned cleanup uses Terraform.

After successful verification, remove temporary files and password variables:

```powershell
Remove-Item -LiteralPath $localLifecycleDir -Recurse -Force
Remove-Item Env:TF_VAR_candidate_sql_password, Env:TF_VAR_candidate_mongo_password -ErrorAction SilentlyContinue
$env:TF_VAR_enable_database_candidate = 'false'
```

Also delete any earlier saved candidate plan. Keep inputs and configuration if
teardown failed. No apply runs automatically after destruction.

## Recreate the D/6 databases locally when needed

Restore the candidate flag/passwords and authenticate/init as above. Keep the
known SQL region `francecentral`; creation can still fail on future admission
or quota changes. This is the database-only stage, with LiveDocs disabled.

Create a new private temporary directory as above, then:

```powershell
$localCandidatePlan = Join-Path $localLifecycleDir 'candidate.tfplan'
terraform "-chdir=environments/development" validate
if ($LASTEXITCODE -ne 0) { throw 'Validation failed' }
terraform "-chdir=environments/development" plan -lock-timeout=5m "-out=$localCandidatePlan"
if ($LASTEXITCODE -ne 0) { throw 'Candidate planning failed' }
$localPlanText = terraform "-chdir=environments/development" show -json $localCandidatePlan
if ($LASTEXITCODE -ne 0) { throw 'Plan export failed' }
[IO.File]::WriteAllText($localPlanJson, ($localPlanText -join "`n"), [Text.UTF8Encoding]::new($false))
python scripts/validate-database-candidate.py $localPlanJson
if ($LASTEXITCODE -ne 0) { throw 'Candidate plan policy rejected the plan' }
```

Review the resource actions, then apply that exact file and reuse the existing
management-API Free checker, without installing database drivers locally:

```powershell
terraform "-chdir=environments/development" apply -lock-timeout=5m $localCandidatePlan
if ($LASTEXITCODE -ne 0) { throw 'Apply failed; investigate partial resources' }
$localNamesFile = Join-Path $localLifecycleDir 'candidate-names.json'
$localNamesText = terraform "-chdir=environments/development" output -json database_candidate
if ($LASTEXITCODE -ne 0) { throw 'Candidate output read failed' }
[IO.File]::WriteAllText($localNamesFile, ($localNamesText -join "`n"), [Text.UTF8Encoding]::new($false))
python scripts/validate-database-candidate.py $localNamesFile --readback $env:ARM_SUBSCRIPTION_ID
if ($LASTEXITCODE -ne 0) { throw 'Azure Free/network readback failed; D/6 remains pending' }
Remove-Item -LiteralPath $localLifecycleDir -Recurse -Force
```

Record only the safe success summary, commit, resource names/regions and action
counts. D/6 readback checks configuration; D/9 checks real driver compatibility
from Azure. D/7 uses `deploy-development-network.ps1` and its wider reviewed plan policy;
do not use the three-resource D/6 validator to approve the full environment.

References: [Azure Blob backend CLI authentication](https://developer.hashicorp.com/terraform/language/backend/azurerm),
[saved destroy plans](https://developer.hashicorp.com/terraform/cli/commands/destroy).
