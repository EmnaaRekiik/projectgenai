# Live PostgreSQL smoke: verifies staff bearer auth and revocation without creating extra accounts.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'
. (Join-Path $PSScriptRoot '_staff_login.ps1')
$h = Get-SmartCampusStaffHeaders -BaseUrl $base
$me = Invoke-RestMethod -Method Get -Uri "$base/auth/me" -Headers $h
if ($me.role -ne 'PLATFORM_ADMIN') { throw 'Role is not PLATFORM_ADMIN.' }
$staff = Invoke-RestMethod -Method Get -Uri "$base/staff" -Headers $h
if (@($staff).Count -lt 1) { throw 'No staff account listed.' }
$catalogue = Invoke-RestMethod -Method Get -Uri "$base/admin/programs" -Headers $h
if ($null -eq $catalogue.total) { throw 'Authenticated catalogue listing failed.' }
Write-Host 'PASS: Login, role, account list and protected catalogue API.' -ForegroundColor Green
Invoke-RestMethod -Method Post -Uri "$base/auth/logout" -Headers $h | Out-Null
try {
    Invoke-RestMethod -Method Get -Uri "$base/auth/me" -Headers $h | Out-Null
    throw 'FAIL: A logged-out token remained valid.'
} catch {
    # PowerShell 5.1's Invoke-RestMethod throws on a non-2xx response.
    $response = $_.Exception.Response
    if ($null -eq $response -or [int]$response.StatusCode -ne 401) { throw }
    Write-Host 'PASS: Logout token revoked (HTTP 401).' -ForegroundColor Green
}
