# Same immutable Invoice bytes, Consumption allocation and launch options as the API.
$ErrorActionPreference = 'Stop'
$passed = $false
$browser = $null
$playwright = $null
try {
    if ($env:D9_RUN_ID -notmatch '^[a-f0-9]{32}$') { throw 'Unbound probe' }
    Set-Location /app
    if (-not (Test-Path /app/Templates/InvoiceTemplate.html) -or -not (Test-Path /app/Templates/InvoiceLineTemplate.html)) { throw 'Missing templates' }
    # The service calls the same install command on first PDF generation.
    & pwsh -NoProfile -File /app/playwright.ps1 install *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Browser install failed' }
    [Reflection.Assembly]::LoadFrom('/app/Microsoft.Playwright.dll') | Out-Null
    $playwright = [Microsoft.Playwright.Playwright]::CreateAsync().GetAwaiter().GetResult()
    $options = [Microsoft.Playwright.BrowserTypeLaunchOptions]::new()
    $options.Headless = $true
    $browser = $playwright.Chromium.LaunchAsync($options).GetAwaiter().GetResult()
    $page = $browser.NewPageAsync().GetAwaiter().GetResult()
    $page.SetContentAsync('<html><body><h1>Synthetic D/9 invoice runtime probe</h1></body></html>').GetAwaiter().GetResult()
    $pdfOptions = [Microsoft.Playwright.PagePdfOptions]::new()
    $pdfOptions.Format = 'A4'
    $pdfOptions.PrintBackground = $true
    $pdf = $page.PdfAsync($pdfOptions).GetAwaiter().GetResult()
    $passed = $pdf.Length -gt 100 -and [Text.Encoding]::ASCII.GetString($pdf, 0, 5) -eq '%PDF-'
} catch {
    # No exception text, file payloads, process output or connection strings in reports.
    $passed = $false
} finally {
    if ($browser) { try { $browser.CloseAsync().GetAwaiter().GetResult() } catch {} }
    if ($playwright) { $playwright.Dispose() }
}
$report = @{ schema = 1; mode = 'invoice'; run_id = $env:D9_RUN_ID; checks = @{ chromium_pdf = $passed }; passed = $passed } | ConvertTo-Json -Compress -Depth 5
Write-Host ('D9_REPORT:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($report)))
# Allow local log collection before Azure removes the stopped job replica.
if ($env:D9_BACKEND -ne 'native-baseline') { Start-Sleep -Seconds 90 }
if (-not $passed) { exit 1 }
