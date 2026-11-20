# The old bootstrap key was disclosed. Rotate it before first-admin setup.
# This does not touch the PostgreSQL password or volume.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$path = Join-Path (Get-Location) '.env'
if (-not (Test-Path $path)) { throw '.env is missing.' }
$bytes = New-Object byte[] 32
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $random.GetBytes($bytes) } finally { $random.Dispose() }
$new = ([BitConverter]::ToString($bytes)).Replace('-', '')
$lines = [System.Collections.Generic.List[string]]::new()
$updated = $false
foreach ($line in [System.IO.File]::ReadAllLines($path)) {
    if ($line.StartsWith('ADMIN_API_KEY=')) {
        if (-not $updated) { $lines.Add('ADMIN_API_KEY=' + $new); $updated = $true }
    } else { $lines.Add($line) }
}
if (-not $updated) { $lines.Add('ADMIN_API_KEY=' + $new) }
[System.IO.File]::WriteAllLines($path, $lines.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Bootstrap key rotated in .env. Its value was not printed.' -ForegroundColor Green
Write-Host 'Run: docker compose up -d --force-recreate api' -ForegroundColor Cyan
