# T8 live end-to-end check of the tuition / payment-terms / admission-rules APIs (PostgreSQL).
# Creates ONE fictitious programme (CHECK-T8-...), publishes it with the reserved demo.invalid source,
# exercises the three resources as staff and as the public, then ARCHIVES the programme in `finally`
# (an archived programme exposes nothing). Needs a platform administrator login.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'
. (Join-Path $PSScriptRoot '_staff_login.ps1')
$headers = Get-SmartCampusStaffHeaders -BaseUrl $base
$json = 'application/json'
function Check([bool] $condition, [string] $message) { if (-not $condition) { throw "FAIL: $message" } }
function Send($method, $uri, $body = $null, $auth = $true) {
    $args2 = @{ Method = $method; Uri = $uri; ContentType = $json }
    if ($auth) { $args2.Headers = $headers }
    if ($null -ne $body) { $args2.Body = ($body | ConvertTo-Json -Compress) }
    Invoke-RestMethod @args2
}

# Number of items in a PUBLIC list. Reads the raw JSON so Windows PowerShell 5.1 quirks with empty or
# single-item arrays cannot distort the count; the raw body is shown when a check fails.
function PublicCount($uri) {
    $raw = (Invoke-WebRequest -Method Get -Uri $uri -UseBasicParsing).Content
    if ($raw -is [byte[]]) { $raw = [Text.Encoding]::UTF8.GetString($raw) }
    $raw = $raw.Trim()
    $script:lastRaw = $raw
    if ($raw -eq '[]') { return 0 }
    return ([regex]::Matches($raw, '"id"\s*:')).Count
}
function CheckCount($uri, [int] $expected, [string] $message) {
    $n = PublicCount $uri
    if ($n -ne $expected) { throw "FAIL: $message (expected $expected, got $n). Raw response: $script:lastRaw" }
}
function StatusOf($method, $uri, $body = $null, $auth = $true) {
    try { Send $method $uri $body $auth | Out-Null; return 200 } catch { return [int]$_.Exception.Response.StatusCode }
}

$institutions = Invoke-RestMethod -Method Get -Uri "$base/institutions"
$iit = $null
foreach ($i in $institutions) { if ($i.code -eq 'IIT') { $iit = $i; break } }
if ($null -eq $iit) { throw 'IIT seed is missing.' }
$evidence = @{ official_source_url = 'https://demo.invalid/donnees-fictives'; verified_at = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString('o') }
$program = $null
try {
    Write-Host '[1/5] Programme creation and publication' -ForegroundColor Cyan
    $code = 'CHECK-T8-' + ([Guid]::NewGuid().ToString('N').Substring(0, 8).ToUpperInvariant())
    $program = Send Post "$base/admin/programs" @{ institution_id = ([guid]$iit.id).ToString('D'); code = $code; title = '[DEMO] Verification T8'; level = 'OTHER' }
    $pid2 = $program.id
    $patch = @{ status = 'PUBLISHED' } + $evidence
    Check ((Send Patch "$base/admin/programs/$pid2" $patch).status -eq 'PUBLISHED') 'programme was not published'
    Write-Host 'PASS' -ForegroundColor Green

    Write-Host '[2/5] Create the three resources (hidden until verified)' -ForegroundColor Cyan
    $payloads = [ordered]@{
        'tuition'         = @{ label = 'Frais annuels'; amount = '1500.00'; academic_year = '2026-2027' }
        'payment-terms'   = @{ label = 'Trois tranches'; academic_year = '2026-2027'; payment_mode = 'INSTALLMENTS'; installments_count = 3; first_payment_percent = '40.00' }
        'admission-rules' = @{ kind = 'ADMISSION'; title = 'Condition test'; description = 'Exemple fictif' }
    }
    $ids = @{}
    foreach ($kind in $payloads.Keys) {
        $ids[$kind] = (Send Post "$base/admin/programs/$pid2/$kind" $payloads[$kind]).id
        CheckCount "$base/programs/$pid2/$kind" 0 "$kind visible before verification"
    }
    Write-Host 'PASS' -ForegroundColor Green

    Write-Host '[3/5] Verify, then the public sees them' -ForegroundColor Cyan
    foreach ($kind in $payloads.Keys) {
        Send Patch "$base/admin/programs/$pid2/$kind/$($ids[$kind])" $evidence | Out-Null
        CheckCount "$base/programs/$pid2/$kind" 1 "$kind not public after verification"
    }
    Write-Host 'PASS' -ForegroundColor Green

    Write-Host '[4/5] Publication status and validity period' -ForegroundColor Cyan
    $tuitionUrl = "$base/admin/programs/$pid2/tuition/$($ids['tuition'])"
    Send Patch $tuitionUrl @{ publication_status = 'ARCHIVED' } | Out-Null
    CheckCount "$base/programs/$pid2/tuition" 0 'archived tariff still public'
    Send Patch $tuitionUrl @{ publication_status = 'PUBLISHED' } | Out-Null
    $past = @{ valid_from = (Get-Date).ToUniversalTime().AddDays(-30).ToString('o'); valid_to = (Get-Date).ToUniversalTime().AddDays(-1).ToString('o') } + $evidence
    Send Patch $tuitionUrl $past | Out-Null
    CheckCount "$base/programs/$pid2/tuition" 0 'expired tariff still public'
    $open = @{ valid_from = $null; valid_to = $null } + $evidence
    Send Patch $tuitionUrl $open | Out-Null
    CheckCount "$base/programs/$pid2/tuition" 1 'open-ended tariff not public'
    Write-Host 'PASS' -ForegroundColor Green

    Write-Host '[5/5] Error handling' -ForegroundColor Cyan
    Check ((StatusOf Post "$base/admin/programs/$pid2/tuition" $payloads['tuition']) -eq 409) 'duplicate tariff should be 409'
    Check ((StatusOf Post "$base/admin/programs/$pid2/tuition" @{ label = 'x1'; amount = '-5'; academic_year = '2026-2027' }) -eq 422) 'negative amount should be 422'
    Check ((StatusOf Post "$base/admin/programs/$pid2/payment-terms" @{ label = 'x1'; academic_year = '2026-2027'; payment_mode = 'FULL'; installments_count = 2 }) -eq 422) 'FULL with instalments should be 422'
    Check ((StatusOf Post "$base/admin/programs/$pid2/tuition" $payloads['tuition'] $false) -eq 401) 'anonymous write should be 401'
    Check ((StatusOf Get "$base/programs/00000000-0000-0000-0000-000000000099/tuition" $null $false) -eq 404) 'unknown programme should be 404'
    Write-Host 'PASS' -ForegroundColor Green
} finally {
    if ($program) {
        Send Delete "$base/admin/programs/$($program.id)" | Out-Null
        Check ((Send Get "$base/admin/programs/$($program.id)").status -eq 'ARCHIVED') 'cleanup: programme not archived'
        Write-Host 'Cleanup: test programme archived (no longer public).' -ForegroundColor Green
    }
}
