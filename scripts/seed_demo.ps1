# Insert FICTITIOUS demonstration data (programmes, specialities, courses, fees, payment terms,
# demo staff accounts) into the running stack. Safe to run several times.
#
#   .\scripts\seed_demo.ps1              # draft programmes (invisible to the public) + demo accounts
#   .\scripts\seed_demo.ps1 -Publish     # also expose them publicly (DEVELOPMENT ONLY)
#   .\scripts\seed_demo.ps1 -NoStaff     # catalogue only
#   .\scripts\seed_demo.ps1 -Remove      # delete everything this script created
#
# Prerequisites: stack running AND image rebuilt after pulling (docker compose up -d --build),
# real administrator already created with bootstrap_admin.ps1.
param([switch]$Publish, [switch]$NoStaff, [switch]$Remove)
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is not installed or not in PATH.' }

$argsList = @('compose', 'exec', '-T')
if ($env:DEMO_STAFF_PASSWORD) { $argsList += @('-e', 'DEMO_STAFF_PASSWORD') }   # forwards the value without printing it
$argsList += @('api', 'python', '-m', 'app.db.seed_demo')
if ($Publish) { $argsList += '--publish' }
if ($NoStaff) { $argsList += '--no-staff' }
if ($Remove)  { $argsList += '--remove' }
if ($Publish -and -not $Remove) { Write-Warning 'Publishing demo data: never do this on a deployment that serves real candidates.' }

& docker @argsList
if ($LASTEXITCODE -ne 0) { throw "seed_demo failed (exit code $LASTEXITCODE)." }
