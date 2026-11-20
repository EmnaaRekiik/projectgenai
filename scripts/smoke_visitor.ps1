# Execute against the running *actual* Docker/PostgreSQL API.
# Never output bearer token or store it in command-line arguments.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8001/api/v1/visitor/sessions'
Write-Host 'Checking SA-25 and SA-26 on PostgreSQL...' -ForegroundColor Cyan

$first = Invoke-RestMethod -Method Post -Uri $base
$second = Invoke-RestMethod -Method Post -Uri $base
$h1 = @{ 'X-Visitor-Token' = $first.token }
$h2 = @{ 'X-Visitor-Token' = $second.token }
try {
    $m1 = Invoke-RestMethod -Method Post -Uri "$base/$($first.id)/messages" -Headers $h1 -ContentType 'application/json; charset=utf-8' -Body '{"content":"Salem, nheb na9ra informatique"}'
    $m2 = Invoke-RestMethod -Method Post -Uri "$base/$($first.id)/messages" -Headers $h1 -ContentType 'application/json; charset=utf-8' -Body '{"content":"Nheb na3ref licence wella ingenieur"}'
    if ($m1.sequence -ne 1 -or $m2.sequence -ne 2) { throw 'Sequence numbers are incorrect.' }
    $context = Invoke-RestMethod -Method Get -Uri "$base/$($first.id)/context" -Headers $h1
    if (@($context.messages).Count -ne 2) { throw 'Conversation context is not persisted.' }
    if ($context.messages[1].content -ne 'Nheb na3ref licence wella ingenieur') { throw 'Conversation order or content is incorrect.' }
    $isolated = Invoke-RestMethod -Method Get -Uri "$base/$($second.id)/context" -Headers $h2
    if (@($isolated.messages).Count -ne 0) { throw 'Messages leaked between visitors.' }
    $denied = $false
    try {
        Invoke-WebRequest -Method Get -Uri "$base/$($first.id)/messages" -Headers $h2 -UseBasicParsing | Out-Null
    } catch {
        if ([int]$_.Exception.Response.StatusCode -eq 404) { $denied = $true } else { throw }
    }
    if (-not $denied) { throw 'Cross-session access was not denied.' }
    Write-Host 'PASS: creation, two-turn PostgreSQL memory, isolated contexts and token ownership.' -ForegroundColor Green
} finally {
    # Destroy smoke-test transcripts (and both session records), even on failure.
    Invoke-RestMethod -Method Delete -Uri "$base/$($first.id)" -Headers $h1 | Out-Null
    Invoke-RestMethod -Method Delete -Uri "$base/$($second.id)" -Headers $h2 | Out-Null
}
