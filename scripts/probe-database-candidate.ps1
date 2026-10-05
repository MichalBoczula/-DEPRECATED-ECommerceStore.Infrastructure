# Run on the Windows operator workstation after the candidate apply succeeds.
param(
  [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]{6,16}$')][string]$Suffix,
  [ValidateSet('first', 'recreated')][string]$Cycle = 'first'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$reportRoot = Join-Path $repoRoot "artifacts/database-gate/$Cycle"
$sourceRoot = Join-Path $repoRoot 'artifacts/database-gate/payments'
$project = Join-Path $repoRoot 'verification/database-gate/dotnet'
New-Item -ItemType Directory -Force $reportRoot | Out-Null

function Get-AzureJson([string]$Url, [string]$Method = 'get') {
  $raw = & az rest --method $Method --url $Url --output json --only-show-errors 2>$null
  if ($LASTEXITCODE -ne 0) { throw 'Azure readback failed; no offer acceptance.' }
  return ($raw -join "`n" | ConvertFrom-Json)
}
function Invoke-Private([string]$Label, [scriptblock]$Command) {
  $log = Join-Path $reportRoot "$Label.private.log"
  & $Command *> $log
  if ($LASTEXITCODE -ne 0) { throw "$Label failed; inspect the private local log. No backend selected." }
  Remove-Item $log
}

try {
  $subscription = & az account show --query id --output tsv --only-show-errors 2>$null
  if ($LASTEXITCODE -ne 0 -or $subscription -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Use az login and select the subscription first.' }
  $scope = "https://management.azure.com/subscriptions/$subscription/resourceGroups/rg-ecommerce-dev/providers"
  $sqlUrl = "$scope/Microsoft.Sql/servers/sql-ecommerce-dev-d6-$Suffix"
  $mongoUrl = "$scope/Microsoft.DocumentDB/mongoClusters/mongo-ecommerce-dev-d6-$Suffix"
  $sql = Get-AzureJson "$sqlUrl/databases/products-gate?api-version=2023-08-01"
  $sqlServer = Get-AzureJson "$sqlUrl`?api-version=2023-08-01"
  $mongo = Get-AzureJson "$mongoUrl`?api-version=2026-06-01"
  $s = $sql.properties
  $m = $mongo.properties
  if ($sql.location -ne 'northeurope' -or $mongo.location -ne 'northeurope' -or
      $s.useFreeLimit -ne $true -or $s.freeLimitExhaustionBehavior -ne 'AutoPause' -or
      $s.maxSizeBytes -ne 34359738368 -or $sql.sku.name -ne 'GP_S_Gen5_2' -or
      $s.minCapacity -ne 0.5 -or $s.autoPauseDelay -ne 60 -or $s.zoneRedundant -ne $false -or
      $s.requestedBackupStorageRedundancy -ne 'Local' -or
      $m.compute.tier -ne 'Free' -or $m.storage.sizeGb -ne 32 -or $m.sharding.shardCount -ne 1 -or
      $m.highAvailability.targetMode -ne 'Disabled' -or $m.serverVersion -ne '8.0' -or
      $m.publicNetworkAccess -ne 'Enabled' -or -not $m.administrator.userName) {
    throw 'Azure offer readback differs from the Free candidate contract. Destroy the candidate; no paid fallback.'
  }
  $connections = Get-AzureJson "$mongoUrl/listConnectionStrings?api-version=2026-06-01" 'post'
  $template = $connections.connectionStrings[0].connectionString
  if (-not $template.StartsWith('mongodb+srv://') -or -not $template.Contains('<password>')) {
    throw 'Unexpected Mongo connection template. Stop and review the service contract privately.'
  }
  $sqlSecret = Read-Host 'SQL password (same as DATABASE_CANDIDATE_SQL_PASSWORD)' -AsSecureString
  $mongoSecret = Read-Host 'Mongo password (same as DATABASE_CANDIDATE_MONGO_PASSWORD)' -AsSecureString
  $sqlPassword = [System.Net.NetworkCredential]::new('', $sqlSecret).Password
  $mongoPassword = [System.Net.NetworkCredential]::new('', $mongoSecret).Password
  $env:D6_SQL_HOST = $sqlServer.properties.fullyQualifiedDomainName
  # Quote the password as a connection-string value; double embedded quotes.
  $quotedPassword = $sqlPassword.Replace('"', '""')
  $env:D6_SQL_CONNECTION_STRING = "Server=$($env:D6_SQL_HOST);Database=products-gate;User ID=d6operator;Password=`"$quotedPassword`";Encrypt=True;TrustServerCertificate=False;Connect Timeout=180"
  $env:D6_MONGO_CONNECTION_STRING = $template.Replace('<user>', [Uri]::EscapeDataString($m.administrator.userName)).Replace('<password>', [Uri]::EscapeDataString($mongoPassword))
  $env:D6_MONGO_HOST = ([Uri]($env:D6_MONGO_CONNECTION_STRING.Replace('mongodb+srv://', 'https://'))).Host
  $fingerprintBytes = [Text.Encoding]::UTF8.GetBytes("$($sql.id)|$($mongo.id)|$Cycle")
  $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($fingerprintBytes)).ToLowerInvariant()
  @{ cycle=$Cycle; timeUtc=[DateTime]::UtcNow.ToString('o'); candidateFingerprint=$fingerprint;
      region='northeurope'; sqlFreeLimit=$true; exhaustion='AutoPause'; mongoTier='Free';
      mongoAssignedAdministrator=$true; backendSelected=$false } |
    ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $reportRoot 'offer-readback.json')
  if (-not (Test-Path (Join-Path $sourceRoot '.git'))) {
    Invoke-Private 'payments-clone' { git clone --no-checkout https://github.com/MichalBoczula/ECommerceStorePayments.git $sourceRoot }
  }
  Invoke-Private 'payments-fetch' { git -C $sourceRoot fetch origin 9663df14cb10886a32fa7850d1ca51537a3da009 }
  Invoke-Private 'payments-checkout' { git -C $sourceRoot checkout --detach 9663df14cb10886a32fa7850d1ca51537a3da009 }
  Invoke-Private 'dotnet-restore' { dotnet restore $project --locked-mode --verbosity quiet }
  Invoke-Private 'dotnet-build' { dotnet build $project --no-restore --verbosity quiet }
  Invoke-Private 'payments-sync' { uv sync --frozen --project $sourceRoot }
  # Run both suites even if one fails, preserving redacted failure evidence.
  $dotnetReport = Join-Path $reportRoot 'dotnet.json'
  $paymentsReport = Join-Path $reportRoot 'payments.json'
  & dotnet run --project $project --no-build --no-restore -- azure-candidate $dotnetReport
  $dotnetStatus = $LASTEXITCODE
  & uv run --frozen --project $sourceRoot python (Join-Path $repoRoot 'verification/database-gate/payments-gate.py') azure-candidate $sourceRoot $paymentsReport
  $paymentsStatus = $LASTEXITCODE
  & python (Join-Path $repoRoot 'scripts/report-database-gate.py') azure-candidate $dotnetReport $paymentsReport
  if ($dotnetStatus -ne 0 -or $paymentsStatus -ne 0 -or $LASTEXITCODE -ne 0) { throw 'Compatibility failed. Keep failed evidence, destroy the candidate, and review a native Mongo alternative.' }
  Write-Host "Cycle $Cycle driver checks passed. Azure deletion/recreation evidence is still required before D/6 acceptance."
}
finally {
  foreach ($name in @('D6_SQL_CONNECTION_STRING', 'D6_MONGO_CONNECTION_STRING', 'D6_SQL_HOST', 'D6_MONGO_HOST')) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
  }
  $sqlPassword = $mongoPassword = $quotedPassword = $template = $null
}
