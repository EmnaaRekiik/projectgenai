# SA-32: runs REAL inference through the already-running FastAPI server.
# No admin login, Docker restart or package installation required.
param(
    [switch]$Validate,
    [switch]$All,
    [int]$MaxScenarios = 0,
    [string[]]$Scenario = @(),
    [ValidateSet('fr','derja','arabizi','mixed')][string]$Language,
    [ValidateSet('welcome','intent','profiling','orientation','reliability','boundaries','memory')][string]$Category
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $root
try {
    $argsList = @('evaluation/run_eval.py')
    if ($Validate) { $argsList += '--validate' }
    elseif ($All) { $argsList += '--all' }
    else { $argsList += '--smoke' }
    if ($MaxScenarios -gt 0) { $argsList += @('--max-scenarios', "$MaxScenarios") }
    foreach ($scenarioId in $Scenario) { $argsList += @('--scenario', $scenarioId) }
    if ($Language) { $argsList += @('--language', $Language) }
    if ($Category) { $argsList += @('--category', $Category) }
    & python @argsList
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed (exit code $LASTEXITCODE)." }
} finally {
    Pop-Location
}
