# T10: runs the SAME evaluation dataset against several LLM profiles and compares them.
#
#   .\scripts\benchmark_models.ps1                       # all profiles in evaluation\models.json, 3 repetitions
#   .\scripts\benchmark_models.ps1 -Only local-qwen      # one profile
#   .\scripts\benchmark_models.ps1 -Smoke -Repetitions 1 # quick dry run (8 scenarios)
#   .\scripts\benchmark_models.ps1 -CompareOnly          # only rebuild the comparison tables
#
# Prerequisites: stack running (docker compose up -d), evaluation\models.json created from
# evaluation\models.example.json, API keys stored in the environment variables named by "api_key_env"
# (never in a file), Ollama running on this computer for local profiles.
# At the end the API is recreated with the settings from .env, whatever happened.
param(
    [string] $ProfilesFile = 'evaluation\models.json',
    [string[]] $Only = @(),
    [int] $Repetitions = 3,
    [switch] $Smoke,
    [switch] $CompareOnly
)
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'
$llmVars = @('LLM_PROVIDER', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY')

function Wait-ApiReady {
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $health = Invoke-RestMethod -Method Get -Uri "$base/health/ready" -TimeoutSec 3
            if ($health.status -eq 'ready') { return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw 'The API did not become ready in 90 seconds (docker compose logs api --tail 40).'
}

if ($CompareOnly) { & python evaluation/compare_models.py; exit $LASTEXITCODE }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is not installed or not in PATH.' }
if (-not (Test-Path $ProfilesFile)) { throw "Missing $ProfilesFile. Copy evaluation\models.example.json to evaluation\models.json and fill it in." }
$config = Get-Content -Raw -Encoding UTF8 $ProfilesFile | ConvertFrom-Json
$selected = @()
foreach ($item in $config.profiles) {
    if ($Only.Count -eq 0 -or $item.name -in $Only) { $selected += $item }
}
if ($selected.Count -eq 0) { throw 'No profile selected.' }
foreach ($item in $selected) {
    if ($item.model -match 'A_COMPLETER' -or $item.base_url -match 'A_COMPLETER') { throw "Profile '$($item.name)' is still a template: fill in model and base_url or exclude it with -Only." }
    if ($item.api_key_env -and -not [Environment]::GetEnvironmentVariable($item.api_key_env)) {
        throw "Profile '$($item.name)': environment variable $($item.api_key_env) is empty. Set it first, e.g. `$env:$($item.api_key_env) = '...'"
    }
}
& python evaluation/run_eval.py --validate
if ($LASTEXITCODE -ne 0) { throw 'Dataset validation failed.' }

try {
    foreach ($item in $selected) {
        Write-Host "=== Profile $($item.name): $($item.model) ($($item.provider)) ===" -ForegroundColor Cyan
        $env:LLM_PROVIDER = $item.provider
        $env:LLM_BASE_URL = $item.base_url
        $env:LLM_MODEL = $item.model
        if ($item.api_key_env) { $env:LLM_API_KEY = [Environment]::GetEnvironmentVariable($item.api_key_env) } else { Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue }
        & docker compose up -d --force-recreate api
        if ($LASTEXITCODE -ne 0) { throw 'docker compose failed.' }
        Wait-ApiReady
        for ($run = 1; $run -le $Repetitions; $run++) {
            Write-Host "--- $($item.name): repetition $run / $Repetitions ---" -ForegroundColor Yellow
            $mode = if ($Smoke) { '--smoke' } else { '--all' }
            & python evaluation/run_eval.py $mode --output-dir "evaluation/results/$($item.name)"
            if ($LASTEXITCODE -ne 0) { Write-Warning "Run $run of $($item.name) failed; continuing." }
        }
    }
} finally {
    foreach ($name in $llmVars) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    Write-Host 'Restoring the API with the settings from .env ...' -ForegroundColor Cyan
    & docker compose up -d --force-recreate api
}
& python evaluation/compare_models.py
Write-Host 'Next: fill the *_score_0_to_3 columns of each manual_review.csv, then run  .\scripts\benchmark_models.ps1 -CompareOnly' -ForegroundColor Green
