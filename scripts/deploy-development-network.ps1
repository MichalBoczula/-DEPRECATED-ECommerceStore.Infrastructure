param(
    [ValidateSet('plan', 'apply')]
    [string]$Action = 'plan'
)

# Local operator execution only. The same remote development state is retained.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$terraformRoot = Join-Path $repoRoot 'environments/development'
foreach ($setting in @('TFSTATE_RESOURCE_GROUP', 'TFSTATE_STORAGE_ACCOUNT', 'TFSTATE_CONTAINER')) {
    if (-not [Environment]::GetEnvironmentVariable($setting)) { throw "Set $setting before running the local lifecycle script" }
}
if ($env:TFSTATE_RESOURCE_GROUP -eq 'rg-ecommerce-dev' -or $env:TFSTATE_CONTAINER -ne 'development-state') {
    throw 'The backend must be the independent development state store'
}
foreach ($setting in @('TF_CLI_ARGS', 'TF_CLI_ARGS_init', 'TF_CLI_ARGS_plan', 'TF_CLI_ARGS_apply')) {
    if ([Environment]::GetEnvironmentVariable($setting)) { throw "Clear $setting; use the complete locked plan" }
}
$versionText = terraform version -json
if ($LASTEXITCODE -ne 0 -or ($versionText | ConvertFrom-Json).terraform_version -ne '1.16.5') {
    throw 'Use Terraform 1.16.5 on PATH'
}
Remove-Item Env:ARM_CLIENT_ID, Env:ARM_CLIENT_SECRET -ErrorAction SilentlyContinue
Remove-Item Env:TF_LOG_PATH -ErrorAction SilentlyContinue
$env:TF_LOG = 'OFF'
$env:TF_IN_AUTOMATION = 'true'
$env:ARM_USE_OIDC = 'false'
$env:ARM_USE_MSI = 'false'
$env:ARM_USE_CLI = 'true'
$env:ARM_USE_AZUREAD = 'true'
$env:TF_WORKSPACE = 'default'
$env:ARM_SUBSCRIPTION_ID = (az account show --query id --output tsv)
if ($LASTEXITCODE -ne 0 -or -not $env:ARM_SUBSCRIPTION_ID) { throw 'Sign in with az login and select the development subscription' }
$env:ARM_TENANT_ID = (az account show --query tenantId --output tsv)
if ($LASTEXITCODE -ne 0 -or -not $env:ARM_TENANT_ID) { throw 'Azure tenant read failed' }
function Assert-LiveDocsArchive {
    if ($env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT -notmatch '^[a-z0-9]{3,24}$') {
        throw 'Set LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT from the persistent foundation output; see docs/livedocs-deployment.md'
    }
    az storage account show --subscription $env:ARM_SUBSCRIPTION_ID --resource-group rg-ecommerce-livedocs-archive `
        --name $env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT --output none
    if ($LASTEXITCODE -ne 0) { throw 'Persistent LiveDocs archive verification failed' }
}

$workDir = Join-Path $env:TEMP ('ecommerce-d7-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $workDir | Out-Null
$planFile = Join-Path $workDir 'network.tfplan'
$jsonFile = Join-Path $workDir 'plan.json'
try {
    terraform "-chdir=$terraformRoot" init -reconfigure -lockfile=readonly `
        "-backend-config=resource_group_name=$env:TFSTATE_RESOURCE_GROUP" `
        "-backend-config=storage_account_name=$env:TFSTATE_STORAGE_ACCOUNT" `
        "-backend-config=container_name=$env:TFSTATE_CONTAINER" `
        '-backend-config=key=ecommerce/development.tfstate' `
        '-backend-config=use_oidc=false' '-backend-config=use_cli=true' '-backend-config=use_azuread_auth=true'
    if ($LASTEXITCODE -ne 0) { throw 'Backend initialization failed' }
    terraform "-chdir=$terraformRoot" validate
    if ($LASTEXITCODE -ne 0) { throw 'Terraform validation failed' }
    terraform "-chdir=$terraformRoot" plan -input=false -lock-timeout=5m "-out=$planFile"
    if ($LASTEXITCODE -ne 0) { throw 'Network planning failed; no apply attempted' }
    $planText = terraform "-chdir=$terraformRoot" show -json $planFile
    if ($LASTEXITCODE -ne 0) { throw 'Plan export failed' }
    [IO.File]::WriteAllText($jsonFile, ($planText -join "`n"), [Text.UTF8Encoding]::new($false))
    python (Join-Path $PSScriptRoot 'validate-network-plan.py') $jsonFile --verify-egress $env:ARM_SUBSCRIPTION_ID
    if ($LASTEXITCODE -ne 0) { throw 'D/7 plan or live egress verification failed; no apply attempted' }
    $plannedVariables = (($planText -join "`n") | ConvertFrom-Json).variables
    # Saved-plan inputs may be "true"/"false" strings; [bool]'false' is also true.
    $liveDocsEnabled = [string]$plannedVariables.enable_livedocs.value -eq 'true'
    if ($liveDocsEnabled) { Assert-LiveDocsArchive }
    if ($Action -eq 'apply') {
        terraform "-chdir=$terraformRoot" apply -input=false -lock-timeout=5m $planFile
        if ($LASTEXITCODE -ne 0) { throw 'Apply failed; inspect partial state and keep the cleanup inputs' }
        if ([string]$plannedVariables.enable_data_services.value -eq 'true') {
            $dataText = terraform "-chdir=$terraformRoot" output -json data_services
            if ($LASTEXITCODE -ne 0) { throw 'Data-services output read failed' }
            [IO.File]::WriteAllText($jsonFile, ($dataText -join "`n"), [Text.UTF8Encoding]::new($false))
            python (Join-Path $PSScriptRoot 'validate-network-plan.py') $jsonFile --data-readback $env:ARM_SUBSCRIPTION_ID
            if ($LASTEXITCODE -ne 0) { throw 'D/8 infrastructure readback failed; retain inputs for investigation or teardown' }
        }
        if ([string]$plannedVariables.enable_database_candidate.value -eq 'true' -and [string]$plannedVariables.enable_database_access.value -ne 'true') {
            $candidateText = terraform "-chdir=$terraformRoot" output -json database_candidate
            if ($LASTEXITCODE -ne 0) { throw 'Database output read failed' }
            [IO.File]::WriteAllText($jsonFile, ($candidateText -join "`n"), [Text.UTF8Encoding]::new($false))
            python (Join-Path $PSScriptRoot 'validate-database-candidate.py') $jsonFile --readback $env:ARM_SUBSCRIPTION_ID
            if ($LASTEXITCODE -ne 0) { throw 'Free database readback failed; retain inputs for investigation or teardown' }
        }
        if ($liveDocsEnabled) {
            $liveText = terraform "-chdir=$terraformRoot" output -json livedocs
            if ($LASTEXITCODE -ne 0) { throw 'LiveDocs output read failed' }
            $live = ($liveText -join "`n") | ConvertFrom-Json
            python (Join-Path $PSScriptRoot 'smoke-livedocs.py') $live.portal_url $live.commit_sha
            if ($LASTEXITCODE -ne 0) { throw 'LiveDocs HTTPS/source verification failed' }
            Assert-LiveDocsArchive
        }
        $networkText = terraform "-chdir=$terraformRoot" output -json network_access
        if ($LASTEXITCODE -ne 0) { throw 'Network output read failed' }
        [IO.File]::WriteAllText($jsonFile, ($networkText -join "`n"), [Text.UTF8Encoding]::new($false))
        if (($networkText | ConvertFrom-Json).database_access_enabled) {
            python (Join-Path $PSScriptRoot 'validate-network-plan.py') $jsonFile --readback $env:ARM_SUBSCRIPTION_ID
            if ($LASTEXITCODE -ne 0) { throw 'ARM readback failed; D/7 live acceptance remains pending' }
        }
    }
}
finally {
    # Plans include credentials even when console values are marked sensitive.
    Remove-Item -LiteralPath $workDir -Recurse -Force
}
