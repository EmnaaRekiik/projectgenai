# One-time bootstrap, all passwords remain in memory and are never written to disk.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$base = 'http://127.0.0.1:8001/api/v1'
$line = Get-Content '.env' | Where-Object { $_ -match '^ADMIN_API_KEY=' } | Select-Object -First 1
if (-not $line) { throw 'ADMIN_API_KEY not configured in .env.' }
$key = $line.Substring('ADMIN_API_KEY='.Length).Trim()
$email = (Read-Host 'Platform administrator email').Trim()
$name = (Read-Host 'Display name').Trim()
$secure = Read-Host 'New administrator password (at least 12 characters)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $json = @{
        email = $email; display_name = $name; password = $password; role = 'PLATFORM_ADMIN'
    } | ConvertTo-Json -Compress
    $user = Invoke-RestMethod -Method Post -Uri "$base/auth/bootstrap" -Headers @{ 'X-Admin-Key' = $key } -ContentType 'application/json' -Body $json
    Write-Host "PASS: First platform administrator created: $($user.email) (no token yet)." -ForegroundColor Green
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    Remove-Variable password, json, secure, key -ErrorAction SilentlyContinue
}
Write-Host 'Next: log in through POST /api/v1/auth/login in Swagger, or run .\scripts\smoke_auth.ps1.'
