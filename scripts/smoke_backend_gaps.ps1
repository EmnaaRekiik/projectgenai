# Non-destructive v0.5.0 smoke: live PostgreSQL migrations, catalogue sub-resources,
# candidate signup/login/token isolation and retention service startup.
# Test data uses DRAFT programmes only and is archived/deleted in finally.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'

Write-Host '[1/5] Migration and service status' -ForegroundColor Cyan
$revision = (docker compose exec -T api python -m alembic current | Out-String)
if ($LASTEXITCODE -ne 0 -or $revision -notmatch '0007_abuse_limits\s+\(head\)') {
    throw "Expected 0007_abuse_limits (head). Actual: $revision"
}
$services = @(docker compose ps --services --status running)
foreach ($name in @('db', 'api', 'retention')) {
    if ($name -notin $services) { throw "Docker service '$name' is not running." }
}
$health = Invoke-RestMethod -Method Get -Uri "$base/health/ready"
if ($health.status -ne 'ready' -or $health.schema -ne 'catalogue-v2') {
    throw 'Readiness endpoint did not confirm the new schema.'
}
Write-Host 'PASS: all three services running, catalogue-v2 ready, Alembic 0007 head.' -ForegroundColor Green

Write-Host '[2/5] Swagger API contracts' -ForegroundColor Cyan
$api = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8001/openapi.json'
$paths = @($api.paths.PSObject.Properties.Name)
foreach ($path in @(
  '/api/v1/candidates/register',
  '/api/v1/candidates/login',
  '/api/v1/candidates/me',
  '/api/v1/programs/{program_id}/courses',
  '/api/v1/admin/programs/{program_id}/specializations',
  '/api/v1/admin/programs/{program_id}/admission-rules',
  '/api/v1/admin/programs/{program_id}/tuition'
)) {
    if ($path -notin $paths) { throw "Missing OpenAPI path: $path" }
}
Write-Host 'PASS: new candidate and catalogue endpoints available in Swagger.' -ForegroundColor Green

Write-Host '[3/5] Independent candidate login and logout' -ForegroundColor Cyan
$guid = [Guid]::NewGuid().ToString('N').Substring(0,12)
$email = "smartcampus-check-$guid@example.org"
$password = ('SC-Check-' + [Guid]::NewGuid().ToString('N') + '!Aa1')
$candidateCreated = $false
$program = $null
$staffHeaders = $null
try {
    $candidate = Invoke-RestMethod -Method Post -Uri "$base/candidates/register" -ContentType 'application/json' -Body (
      @{ email=$email; display_name='Verification technique'; password=$password } | ConvertTo-Json -Compress
    )
    $candidateCreated = $true
    if ($candidate.email -ne $email) { throw 'Candidate signup returned unexpected identity.' }
    $login = Invoke-RestMethod -Method Post -Uri "$base/candidates/login" -ContentType 'application/json' -Body (
      @{ email=$email; password=$password } | ConvertTo-Json -Compress
    )
    $candidateHeaders = @{ Authorization = "Bearer $($login.access_token)" }
    $mine = Invoke-RestMethod -Method Get -Uri "$base/candidates/me" -Headers $candidateHeaders
    if ($mine.email -ne $email) { throw 'Candidate profile belongs to a different user.' }
    $patch = Invoke-RestMethod -Method Patch -Uri "$base/candidates/me" -Headers $candidateHeaders -ContentType 'application/json' -Body '{"education_level":"Bac sciences","interests":["informatique","maths"]}'
    if (@($patch.interests).Count -ne 2) { throw 'Candidate profile update failed.' }
    Invoke-RestMethod -Method Post -Uri "$base/candidates/logout" -Headers $candidateHeaders | Out-Null
    $revoked = $false
    try {
        Invoke-RestMethod -Method Get -Uri "$base/candidates/me" -Headers $candidateHeaders | Out-Null
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { $revoked = $true }
        else { throw }
    }
    if (-not $revoked) { throw 'Candidate token was not revoked on logout.' }
    Write-Host 'PASS: candidate signup, password login, profile update, logout and revocation.' -ForegroundColor Green

    Write-Host '[4/5] Protected programme details on PostgreSQL' -ForegroundColor Cyan
    . (Join-Path $PSScriptRoot '_staff_login.ps1')
    $staffHeaders = Get-SmartCampusStaffHeaders -BaseUrl $base
    $institutions = Invoke-RestMethod -Method Get -Uri "$base/institutions"
    $iit = $null
    foreach ($entry in $institutions) {
        if ($entry.code -eq 'IIT') { $iit = $entry; break }
    }
    if (-not $iit) { throw 'IIT was not seeded.' }
    $code = 'GAP-' + [Guid]::NewGuid().ToString('N').Substring(0,12).ToUpperInvariant()
    $program = Invoke-RestMethod -Method Post -Uri "$base/admin/programs" -Headers $staffHeaders -ContentType 'application/json' -Body (
        @{ institution_id=([guid]$iit.id).ToString('D'); code=$code;
           title='Programme fictif pour verification technique'; level='OTHER' } | ConvertTo-Json -Compress
    )
    if ($program.status -ne 'DRAFT') { throw 'Test programme was published unexpectedly!' }
    $p = "$base/admin/programs/$($program.id)"
    $specialty = Invoke-RestMethod -Method Post -Uri "$p/specializations" -Headers $staffHeaders -ContentType 'application/json' -Body '{"code":"CHECK-AI","title":"Specialite fictive"}'
    $courseBody = @{ code='CHECK-101'; title='Matiere fictive'; semester=1; credits=3;
                     specialization_id=$specialty.id } | ConvertTo-Json -Compress
    $course = Invoke-RestMethod -Method Post -Uri "$p/courses" -Headers $staffHeaders -ContentType 'application/json' -Body $courseBody
    $rule = Invoke-RestMethod -Method Post -Uri "$p/admission-rules" -Headers $staffHeaders -ContentType 'application/json' -Body '{"kind":"PREREQUISITE","title":"Prerequis fictif","description":"Donnee de test uniquement"}'
    $fee = Invoke-RestMethod -Method Post -Uri "$p/tuition" -Headers $staffHeaders -ContentType 'application/json' -Body '{"label":"Montant fictif non publie","amount":"100.00","currency":"TND","academic_year":"2026-2027"}'
    if ($course.specialization_id -ne $specialty.id -or $rule.kind -ne 'PREREQUISITE' -or [decimal]$fee.amount -ne 100) {
        throw 'Academic relation or programme detail persistence is invalid.'
    }
    $public = Invoke-RestMethod -Method Get -Uri "$base/programs"
    if (@($public.items | Where-Object { $_.id -eq $program.id }).Count -ne 0) {
        throw 'Unverified draft was exposed in the public catalogue.'
    }
    Write-Host 'PASS: 4 programme detail types persisted; course linked to speciality; no public draft leak.' -ForegroundColor Green

    Write-Host '[5/5] Retention worker' -ForegroundColor Cyan
    $purge = (docker compose exec -T api python -m app.db.purge_expired | Out-String)
    if ($LASTEXITCODE -ne 0 -or $purge -notmatch 'visitor_sessions') {
        throw "Retention job failed: $purge"
    }
    Write-Host 'PASS: retention purge executed against PostgreSQL.' -ForegroundColor Green
}
finally {
    if ($program -and $staffHeaders) {
        try { Invoke-RestMethod -Method Delete -Uri "$base/admin/programs/$($program.id)" -Headers $staffHeaders | Out-Null }
        catch { Write-Warning "Test programme cleanup failed; archive it manually: $($program.id)" }
    }
    if ($candidateCreated) {
        try {
            $login = Invoke-RestMethod -Method Post -Uri "$base/candidates/login" -ContentType 'application/json' -Body (
              @{ email=$email; password=$password } | ConvertTo-Json -Compress
            )
            Invoke-RestMethod -Method Delete -Uri "$base/candidates/me" -Headers @{Authorization="Bearer $($login.access_token)"} | Out-Null
        } catch { Write-Warning 'Candidate test account cleanup failed. Remove it manually if necessary.' }
    }
    Remove-Variable password, candidateHeaders, login, staffHeaders -ErrorAction SilentlyContinue
}
Write-Host 'PASS: SmartCampus 0.5.0 backend gap smoke completed.' -ForegroundColor Green
