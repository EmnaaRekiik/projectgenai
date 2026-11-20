# Full catalogue write/read/archive test against live PostgreSQL.
# Uses ONLY a fictitious DRAFT programme and archives it afterwards.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'
. (Join-Path $PSScriptRoot "_staff_login.ps1")
$headers = Get-SmartCampusStaffHeaders -BaseUrl $base
# On Windows PowerShell 5.1, @(Invoke-RestMethod ...) can wrap a JSON array
# as ONE pipeline object. Filtering then returns the entire two-item array,
# making $iit.id contain both IIT and ISB IDs. Iterate explicitly instead.
$institutions = Invoke-RestMethod -Method Get -Uri "$base/institutions"
$iit = $null
foreach ($institution in $institutions) {
    if ($institution.code -eq 'IIT') {
        $iit = $institution
        break
    }
}
if ($null -eq $iit) { throw 'IIT seed is missing.' }
# A GUID cast enforces that exactly one institutional UUID is sent to FastAPI.
$institutionId = ([guid]::Parse([string]($iit.id))).ToString('D')

$programCode = 'CHECK-' + ([Guid]::NewGuid().ToString('N').Substring(0,12).ToUpperInvariant())
$body = @{
  institution_id = $institutionId
  code = $programCode
  title = 'Brouillon de verification technique'
  level = 'OTHER'
  description = 'Test API: jamais une formation officielle.'
} | ConvertTo-Json
$created = $null
try {
    $created = Invoke-RestMethod -Method Post -Uri "$base/admin/programs" -Headers $headers -ContentType 'application/json' -Body $body
    if ($created.status -ne 'DRAFT') { throw 'New programme was not a draft.' }
    $read = Invoke-RestMethod -Method Get -Uri "$base/admin/programs/$($created.id)" -Headers $headers
    if ($read.code -ne $programCode) { throw 'Draft was not persisted.' }
    $public = Invoke-RestMethod -Method Get -Uri "$base/programs"
    if (@($public.items | Where-Object { $_.id -eq $created.id }).Count -ne 0) { throw 'Unverified draft leaked to public API.' }
    $update = Invoke-RestMethod -Method Patch -Uri "$base/admin/programs/$($created.id)" -Headers $headers -ContentType 'application/json' -Body '{"title":"Brouillon technique modifie"}'
    if ($update.title -ne 'Brouillon technique modifie') { throw 'PATCH did not persist.' }
    Write-Host 'PASS: PostgreSQL draft create, admin read, public privacy and PATCH.' -ForegroundColor Green
} finally {
    if ($created) {
        Invoke-RestMethod -Method Delete -Uri "$base/admin/programs/$($created.id)" -Headers $headers | Out-Null
        $archived = Invoke-RestMethod -Method Get -Uri "$base/admin/programs/$($created.id)" -Headers $headers
        if ($archived.status -ne 'ARCHIVED') { throw 'Archive verification failed.' }
        Write-Host 'PASS: record archived; nothing was published.' -ForegroundColor Green
    }
}
