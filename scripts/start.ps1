# Start SmartCampus AI from a clean Windows PowerShell prompt.
# Generates strong random local secrets once; never overwrites existing .env.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))

function New-HexSecret {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '')
}

if (-not (Test-Path '.env')) {
    $template = [System.IO.File]::ReadAllText((Join-Path (Get-Location) '.env.example'))
    $template = $template.Replace('REPLACE_WITH_A_LONG_RANDOM_PASSWORD', (New-HexSecret))
    $template = $template.Replace('REPLACE_WITH_A_DIFFERENT_RANDOM_KEY_AT_LEAST_32_CHARACTERS', (New-HexSecret))
    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location) '.env'),
        $template,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Host 'Created local .env with separate random PostgreSQL and admin keys.' -ForegroundColor Green
} else {
    Write-Host 'Existing .env kept unchanged.' -ForegroundColor Cyan
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker was not found. Install/start Docker Desktop and rerun this script.'
}
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop engine is not running.' }

docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed; check Docker logs.' }

# Do not seed before the entrypoint has finished applying Alembic migrations.
$apiContainer = (docker compose ps -q api).Trim()
if (-not $apiContainer) { throw 'API container was not created.' }
$healthy = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    $state = (docker inspect --format '{{.State.Health.Status}}' $apiContainer 2>$null)
    if ($state -eq 'healthy') { $healthy = $true; break }
    if ($state -eq 'unhealthy') { break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    docker compose logs --tail=80 api
    throw 'API container did not become healthy; see the logs above.'
}

docker compose exec -T api python -m app.db.seed
if ($LASTEXITCODE -ne 0) { throw 'Institution seed failed; check docker compose logs api.' }

Write-Host 'SmartCampus AI is running. Checking the API:' -ForegroundColor Green
& (Join-Path $PSScriptRoot 'smoke.ps1')
