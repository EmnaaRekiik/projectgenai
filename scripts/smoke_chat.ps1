# Run only after configuring a REAL local/hosted LLM and restarting Docker.
# Verifies two real inference calls and durable multi-turn memory in PostgreSQL.
# Secrets and candidate text are not printed to the terminal.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8001/api/v1/visitor/sessions'
Write-Host 'Checking SA-36/SA-37 with a real configured model...' -ForegroundColor Cyan

$session = Invoke-RestMethod -Method Post -Uri $base
$header = @{ 'X-Visitor-Token' = $session.token }
try {
    $request1 = @{ content = 'Salem, ena nheb na9ra informatique. Tnajem tsa3edni?' } | ConvertTo-Json -Compress
    $one = Invoke-RestMethod -Method Post -Uri "$base/$($session.id)/chat" `
        -Headers $header -ContentType 'application/json; charset=utf-8' -TimeoutSec 360 -Body ([System.Text.Encoding]::UTF8.GetBytes($request1))
    if ($one.user_message.sequence -ne 1 -or $one.assistant_message.sequence -ne 2) {
        throw 'First exchange was not stored in sequence.'
    }
    if ($one.assistant_message.role -ne 'assistant' -or [string]::IsNullOrWhiteSpace($one.assistant_message.content)) {
        throw 'First real LLM response is empty or invalid.'
    }

    $request2 = @{ content = 'Tnajem tfakker chnouwa 9otlek nheb na9ra?' } | ConvertTo-Json -Compress
    $two = Invoke-RestMethod -Method Post -Uri "$base/$($session.id)/chat" `
        -Headers $header -ContentType 'application/json; charset=utf-8' -TimeoutSec 360 -Body ([System.Text.Encoding]::UTF8.GetBytes($request2))
    if ($two.user_message.sequence -ne 3 -or $two.assistant_message.sequence -ne 4) {
        throw 'Second exchange was not stored in sequence.'
    }
    $history = Invoke-RestMethod -Method Get -Uri "$base/$($session.id)/messages" -Headers $header
    if (@($history.items).Count -ne 4) { throw 'PostgreSQL does not contain exactly four messages.' }
    if ($history.items[0].role -ne 'user' -or $history.items[1].role -ne 'assistant' -or
        $history.items[2].role -ne 'user' -or $history.items[3].role -ne 'assistant') {
        throw 'History roles are out of order.'
    }
    Write-Host "PASS: 2 live model calls, 4 persisted messages, multi-turn context (model: $($two.model))." -ForegroundColor Green
    Write-Host 'NOTE: A fluent reply and correct recollection must also be reviewed manually (SA-33/SA-34/SA-38).' -ForegroundColor Yellow
} finally {
    # Cleanup persists even if the model request fails; no test transcript left behind.
    Invoke-RestMethod -Method Delete -Uri "$base/$($session.id)" -Headers $header | Out-Null
}
