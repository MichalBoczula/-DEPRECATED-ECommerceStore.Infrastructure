# D/9: business apps in the existing development environment

Keep the successful D/8 deployment. This runbook uses the same remote state and SQL/Mongo resources. Run commands in a PowerShell terminal at the repository root. Terraform must be **1.16.5**, Python must be on PATH, and Azure CLI must be signed into the development subscription. Retain the existing database passwords; these steps do not rotate them.

The rollout has two stages: create identities and two manual verification jobs, then deploy the five business apps after the complete Azure database proof passes. Jobs use Consumption, one replica, no retries, and explicit timeouts. They have no schedule. No workstation-IP rule, private endpoint, NAT gateway or paid logging workspace is added.

## 1. Pull the merged implementation and publish the verification image

```powershell
git switch main
git pull --ff-only
terraform version
az account show --query '{subscription:id,tenant:tenantId}' --output json
az extension add --name containerapp --upgrade
```

Use Azure CLI **2.79 or newer**: job log collection is provided by the Container Apps extension. Upgrade the CLI if its version is older.

In this repository's GitHub **Settings → Secrets and variables → Actions**, configure `DOCKERHUB_USERNAME` as `mb0101` and `DOCKERHUB_TOKEN` as a token allowed to push `mb0101/ecommerce-store-database-gate`. These are image-publication credentials; the workflow has no Azure credentials and does not deploy infrastructure.

Run **Actions → Publish D9 verification image → Run workflow**, on `main`. It tests both retained driver suites against native SQL/Mongo, tests the portable helper image, and generates a PDF using the exact Invoice image at 1 CPU / 2 GiB. It pushes the already-tested helper without rebuilding. Copy the complete immutable reference from its successful summary:

```powershell
$env:TF_VAR_database_gate_image = 'mb0101/ecommerce-store-database-gate@sha256:PASTE_THE_64_CHARACTER_DIGEST'
```

The local checker verifies the registry manifest digest, Linux/amd64 platform, retained Payments commit and current harness source hash. Publish again if a later infrastructure change modifies the harness. Do not substitute a tag or invent a digest.

## 2. Restore the existing session inputs

If you still have the D/8 terminal open, keep its passwords and archive account. These fixed values match the current development deployment:

```powershell
$env:TFSTATE_RESOURCE_GROUP = 'rg-ecommerce-terraform-state'
$env:TFSTATE_STORAGE_ACCOUNT = 'stecomtfc3229fd85c06d3'
$env:TFSTATE_CONTAINER = 'development-state'
$env:TF_VAR_enable_shared_environment = 'true'
$env:TF_VAR_enable_livedocs = 'true'
$env:TF_VAR_enable_database_candidate = 'true'
$env:TF_VAR_enable_data_services = 'true'
$env:TF_VAR_candidate_suffix = 'mike2026'
$env:TF_VAR_candidate_sql_location = 'francecentral'
$env:TF_VAR_enable_business_runtime = 'false'
$env:TF_VAR_enable_business_apps = 'false'
$env:TF_VAR_enable_database_access = 'false'

if (-not $env:TF_VAR_candidate_sql_password) {
    $env:TF_VAR_candidate_sql_password = [pscredential]::new(
        'unused', (Read-Host 'Existing SQL password' -AsSecureString)
    ).GetNetworkCredential().Password
}
if (-not $env:TF_VAR_candidate_mongo_password) {
    $env:TF_VAR_candidate_mongo_password = [pscredential]::new(
        'unused', (Read-Host 'Existing Mongo password' -AsSecureString)
    ).GetNetworkCredential().Password
}

if (-not $env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT) {
    $accounts = @(az storage account list --resource-group rg-ecommerce-livedocs-archive `
        --query "[?tags.lifecycle=='persistent-archive'].name" --output tsv)
    if ($LASTEXITCODE -ne 0 -or $accounts.Count -ne 1) { throw 'Expected the existing persistent archive account' }
    $env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT = $accounts[0].Trim()
}
```

Do not apply the staging flags again once the business apps are deployed: disabling apps would request deletion, which the deployment checker rejects. For subsequent runs keep the flags at their deployed values.

## 3. Write four database secrets into the existing business vault

```powershell
python scripts/configure-development-database-secrets.py
if ($LASTEXITCODE -ne 0) { throw 'Database secret setup failed' }
```

The helper reads safe Terraform outputs and writes four secrets through ARM using the existing administrator passwords. Secret values are absent from CLI arguments, console output and Terraform configuration. The operator needs `Microsoft.KeyVault/vaults/secrets/write` at the deployed vault and permission to create/delete role assignments in the development resource group (for example, its Owner role). The existing GitHub deployment identity deliberately lacks role-assignment delegation; D/9 apply and complete teardown use this local operator session. ARM secret management works with the existing subnet-only data-plane ACL; no firewall exception is needed.

The three Mongo secrets share the existing `d6operator` credential while the apps receive distinct database names. Per-service database users are later hardening, not a D/9 claim. Stripe remains disabled.

## 4. Apply the identity and job stage

```powershell
$env:TF_VAR_enable_business_runtime = 'true'
Remove-Item Env:TF_VAR_database_aca_ipv4 -ErrorAction SilentlyContinue
.\scripts\deploy-development-network.ps1 -Action plan
.\scripts\deploy-development-network.ps1 -Action apply
```

With unchanged D/8 resources, expect **16 creates**: six identities, six secret-scoped Key Vault read roles, two container-scoped Blob roles and two manual jobs. Business apps are still disabled. Existing database password fields may appear as sensitive updates; do not change the passwords. The plan rejects replacements, paid profiles, broad roles and raw runtime secret values.

Each app gets its own identity; BFF receives no secret role. The gate identity can read only Products' SQL and Users' Mongo connection secrets. Products can access `photos`, Invoice can access `invoices`. Those Blob grants prepare D/12; they do not implement application storage adapters.

## 5. Discover Azure outbound IPs and enable narrow database access

```powershell
$env:ARM_SUBSCRIPTION_ID = (az account show --query id --output tsv)
if ($LASTEXITCODE -ne 0 -or -not $env:ARM_SUBSCRIPTION_ID) { throw 'Azure account read failed' }

python scripts/discover-aca-egress.py --subscription $env:ARM_SUBSCRIPTION_ID `
    --app ca-ecommerce-dev-livedocs `
    --job job-ecommerce-dev-database-gate --job job-ecommerce-dev-invoice-probe `
    --output environments/development/database-access.auto.tfvars.json
if ($LASTEXITCODE -ne 0) { throw 'ACA egress discovery failed' }

$env:TF_VAR_enable_database_access = 'true'
.\scripts\deploy-development-network.ps1 -Action plan
.\scripts\deploy-development-network.ps1 -Action apply
```

Discovery reads every existing source and only writes the ignored local input after complete success. Do not replace an empty discovery result with your public IP or ACA's ingress IP. The full union is bounded at 256 addresses; larger sets fail without truncation. SQL/Mongo public endpoints are enabled with exactly one single-IP rule per reported outbound address, with no “allow all Azure services” rule. Discovery and ARM readback prove configuration; the next step proves the pinned drivers work against these endpoints.

## 6. Run the retained Azure database suites

```powershell
python scripts/verify-business-runtime.py --mode database
if ($LASTEXITCODE -ne 0) { throw 'Azure database compatibility failed; keep business apps disabled' }
$env:D9_DATABASE_REPORT = Join-Path $PWD 'artifacts/d9/database-proof.json'
```

This starts one bounded manual job inside the existing ACA environment. It runs all **47** retained SQL/Mongo checks using the D/5 .NET packages and Payments source/lockfile. It creates isolated test schemas/collections, tests SQL writes/constraints, unchanged readiness, Mongo transactions/change streams and cleanup, and preserves the existing application readiness contracts. It does not run business seed data or select a production backend.

Only a complete report from this exact execution and run ID, with Azure status `Succeeded`, is accepted. Native CI reports cannot satisfy the Azure gate. The local report contains fixed check labels, image/resource identities and booleans; arbitrary logs, exceptions, credentials and document payloads are withheld. It expires after 24 hours and is tied to the current subscription, candidate, release, images and outbound IP set.

Job completion includes a 90-second collection window. If logs cannot be collected or a case fails, no proof is produced. Keep the resources and passwords for investigation; do not widen access or bypass the check. Azure compatibility is not established by passing CI alone.

## 7. Deploy the five apps

```powershell
$env:TF_VAR_enable_business_apps = 'true'
.\scripts\deploy-development-network.ps1 -Action plan
.\scripts\deploy-development-network.ps1 -Action apply
```

Expect **five app creates**, with the identities, jobs and D/8 resources retained. The apply script requires the matching database proof before any app create/update. Products, Users, Invoice and Payments use internal HTTPS ingress; BFF is the only public business app. LiveDocs remains the sixth documentation app. All apps use Consumption, `min_replicas=0`, `max_replicas=1`, immutable D/5 images, and their recorded health paths. BFF `/health` is process-only; downstream checks happen separately.

Invoice receives 1 CPU / 2 GiB; the other apps receive 0.25 CPU / 0.5 GiB. Products' automatic migrations are disabled for normal replicas. Internal URLs are derived from the deployed environment domain and contain no localhost addresses. Forwarded HTTPS handling is enabled for the .NET services behind ACA ingress so their HTTPS redirection does not loop. The apps rely on the ACA ingress boundary for proxy trust.

## 8. Refresh all sources and verify runtime

New apps can add outbound addresses. Refresh the full union immediately:

```powershell
python scripts/discover-aca-egress.py --subscription $env:ARM_SUBSCRIPTION_ID `
    --app ca-ecommerce-dev-livedocs --app ca-ecommerce-dev-products `
    --app ca-ecommerce-dev-users --app ca-ecommerce-dev-invoice `
    --app ca-ecommerce-dev-payments --app ca-ecommerce-dev-bff `
    --job job-ecommerce-dev-database-gate --job job-ecommerce-dev-invoice-probe `
    --output environments/development/database-access.auto.tfvars.json
if ($LASTEXITCODE -ne 0) { throw 'Full ACA egress discovery failed' }

.\scripts\deploy-development-network.ps1 -Action plan
.\scripts\deploy-development-network.ps1 -Action apply

# Refresh the database proof against the final address set.
python scripts/verify-business-runtime.py --mode database
if ($LASTEXITCODE -ne 0) { throw 'Final Azure database verification failed' }
python scripts/verify-business-runtime.py --mode runtime --database-report $env:D9_DATABASE_REPORT
if ($LASTEXITCODE -ne 0) { throw 'D/9 runtime verification failed' }

terraform '-chdir=environments/development' output -json business_runtime
```

An ACL-only reconciliation with no app changes can run before refreshing the proof. If the first app apply ends with an egress readback mismatch after Azure created the apps, preserve the state and continue this full discovery/reconciliation step. If that plan also changes an app, rerun database verification with the currently deployed address set before applying; do not bypass proof validation.

Runtime verification requires all five live/ready checks, all four BFF schema routes from inside ACA, public BFF health, and denial of direct public access to each internal app. A second manual job runs the exact Invoice image and produces a synthetic Chromium PDF at the same allocation and launch options. The safe report is `artifacts/d9/runtime-proof.json`. Tests do not publish a PDF or business data.

Keep both safe reports as D/9 evidence. D/9 acceptance remains pending until this Azure run passes. Real business migrations/seed, frontend CORS, Azure Blob adapters and Stripe flows remain D/10–D/13. D/7's separate outside-source database denial exercise remains pending until actually run; app ingress denial does not stand in for that test.

## Failure and cleanup

RBAC propagation, cold starts and SQL resume can delay startup. The checks are bounded and retain normal readiness; a failed check remains failed. Raw diagnostics belong in the operator's private Azure session. Never paste secrets, Terraform state or raw plan JSON into an issue.

Both jobs exit after their bounded execution; they do not poll forever or run on a schedule. The runtime checker does not automatically delete or stop the environment when a local terminal closes. Keep all deployed flags and passwords for retry or the existing [complete destroy runbook](development-network-access.md). Use the complete Terraform destroy path; never delete the state store or persistent archive as part of development cleanup.

Official references: [ACA jobs and manual template overrides](https://learn.microsoft.com/azure/container-apps/jobs), [Key Vault references](https://learn.microsoft.com/azure/container-apps/manage-secrets), [job log CLI](https://learn.microsoft.com/cli/azure/containerapp/job/logs), [internal communication](https://learn.microsoft.com/azure/container-apps/communicate-between-microservices).
