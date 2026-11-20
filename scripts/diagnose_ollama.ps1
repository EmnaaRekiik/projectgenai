# Tests a real native Ollama inference call, bypassing FastAPI.
# It distinguishes model loading/inference latency from Docker connectivity.
$ErrorActionPreference = 'Stop'
Write-Host 'Checking Ollama model execution on Windows...' -ForegroundColor Cyan

$model = 'qwen3.5:4b'
$body = @{
    model = $model
    stream = $false
    think = $false
    messages = @(@{ role = 'user'; content = 'Salem, chnowa t9oul l etudiant yheb informatique? Jawb b jumla wa7da.' })
    options = @{ num_predict = 96; temperature = 0.2 }
} | ConvertTo-Json -Depth 8 -Compress

$watch = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/chat' `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 300
} finally {
    $watch.Stop()
    Write-Host ("Elapsed wall time: {0:n1} s" -f $watch.Elapsed.TotalSeconds)
}
if ([string]::IsNullOrWhiteSpace($result.message.content)) {
    throw 'Ollama returned no visible text. Inspect ollama ps and test a smaller model.'
}
Write-Host "PASS: Native Ollama returned a response with thinking disabled." -ForegroundColor Green
Write-Host "Response: $($result.message.content)"
if ($result.eval_duration -and $result.eval_count) {
    $seconds = [double]$result.eval_duration / 1e9
    if ($seconds -gt 0) {
        Write-Host ("Generation speed: {0:n1} tokens/s" -f ([double]$result.eval_count / $seconds))
    }
}
Write-Host 'Current execution (CPU/GPU):' -ForegroundColor Cyan
ollama ps
