# SmartCampus AI v0.4.0 - targeted live LLM diagnostics.
# Read-only to PostgreSQL: no records, credentials, or user prompts are printed.
# Run from D:\SmartCampus_AI_Backend_v1 in Windows PowerShell.
$ErrorActionPreference = 'Stop'
Write-Host 'SmartCampus AI: diagnosing FastAPI -> Ollama (one real model request)' -ForegroundColor Cyan

Write-Host '\n[1/3] Docker containers:' -ForegroundColor Cyan
docker compose ps
if ($LASTEXITCODE -ne 0) { throw 'docker compose ps failed' }

Write-Host '\n[2/3] Ollama currently loaded models:' -ForegroundColor Cyan
ollama ps
if ($LASTEXITCODE -ne 0) { Write-Host 'ollama ps failed; confirm Ollama is running on Windows.' -ForegroundColor Yellow }

Write-Host '\n[3/3] Call the exact backend provider with the real SmartCampus prompt:' -ForegroundColor Cyan
$python = @'
import sys, time
import httpx
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.llm.context import verified_programme_context, compose_prompt
from app.llm.provider import OpenAICompatibleClient

s = get_settings()
print('Provider:', s.llm_provider)
print('Model:', s.llm_model or '(not configured)')
print('Base URL:', s.llm_base_url or '(not configured)')
print('Timeout:', s.llm_timeout_seconds, 'seconds')
print('Max output tokens:', s.llm_max_output_tokens)

if not s.llm_base_url or not s.llm_model:
    print('FAIL: missing LLM configuration in the API container')
    sys.exit(2)

base = s.llm_base_url.rstrip('/')
if base.endswith('/v1'):
    base = base[:-3]
try:
    with httpx.Client(timeout=10.0) as http:
        tags = http.get(base + '/api/tags')
        print('Ollama /api/tags HTTP:', tags.status_code)
        tags.raise_for_status()
        models = [item.get('name', '') for item in tags.json().get('models', [])]
        print('Requested model is in Ollama list:', s.llm_model in models)
except Exception as exc:
    print('FAIL: Docker-to-Ollama network:', type(exc).__name__, str(exc)[:250])
    sys.exit(3)

try:
    with get_session_factory()() as db:
        catalogue, _sources = verified_programme_context(db)
        messages, _truncated = compose_prompt([], 'Salem, ena nheb na9ra informatique. Tnajem tsa3edni?', catalogue)
    print('Prompt message count:', len(messages))
    print('Prompt characters:', sum(len(m.content) for m in messages))
    started = time.perf_counter()
    result = OpenAICompatibleClient().generate(messages, s)
    elapsed = time.perf_counter() - started
    print('PASS: provider.generate succeeded')
    print('Elapsed seconds:', round(elapsed, 1))
    print('Response characters:', len(result.content))
    print('Model returned:', result.model)
except Exception as exc:
    print('FAIL: provider.generate:', type(exc).__name__, str(exc)[:180])
    cause = exc.__cause__
    if isinstance(cause, httpx.HTTPStatusError):
        print('Ollama HTTP status:', cause.response.status_code)
        # Only a fixed, synthetic test prompt was sent. Do not dump full response bodies.
        print('Ollama error excerpt:', cause.response.text[:350])
    elif cause is not None:
        print('Underlying error type:', type(cause).__name__)
        print('Underlying error:', str(cause)[:280])
    else:
        print('No chained underlying error')
    sys.exit(4)
'@
$python | docker compose exec -T api python -
if ($LASTEXITCODE -ne 0) {
    Write-Host '\nBackend provider diagnostic failed. Share the output above (not your .env).' -ForegroundColor Yellow
} else {
    Write-Host '\nProvider test passed. Re-run .\scripts\smoke_chat.ps1 to confirm the full HTTP + PostgreSQL flow.' -ForegroundColor Green
}
