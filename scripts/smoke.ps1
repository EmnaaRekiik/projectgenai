$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8001'

$ready = Invoke-RestMethod -Uri "$base/api/v1/health/ready" -Method Get
if ($ready.status -ne 'ready') { throw 'Readiness endpoint did not report ready.' }

$institutions = @(Invoke-RestMethod -Uri "$base/api/v1/institutions" -Method Get)
$codes = @($institutions | ForEach-Object { $_.code })
if ('IIT' -notin $codes -or 'ISB' -notin $codes) {
    throw 'Expected IIT and ISB records are missing.'
}

$openapi = Invoke-RestMethod -Uri "$base/openapi.json" -Method Get
if (-not $openapi.info.title.StartsWith('SmartCampus AI')) {
    throw 'OpenAPI metadata does not match SmartCampus AI.'
}

Write-Host 'PASS: PostgreSQL schema, IIT/ISB seed data and OpenAPI are available.' -ForegroundColor Green
Write-Host 'Swagger: http://127.0.0.1:8001/docs' -ForegroundColor Cyan
Write-Host 'Public API: http://127.0.0.1:8001/api/v1/programs' -ForegroundColor Cyan
