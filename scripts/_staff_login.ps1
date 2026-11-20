# Dot-source this from other scripts to get a test-only bearer header.
function Get-SmartCampusStaffHeaders {
    param([string] $BaseUrl = 'http://127.0.0.1:8001/api/v1')
    $email = (Read-Host 'Platform admin email').Trim()
    $secret = Read-Host 'Platform admin password' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $payload = @{ email = $email; password = $password } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType 'application/json' -Body $payload
        if (-not $response.access_token) { throw 'No staff access token returned by API.' }
        if ($response.user.role -ne 'PLATFORM_ADMIN') { throw 'This smoke test needs a platform administrator.' }
        return @{ Authorization = "Bearer $($response.access_token)" }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        Remove-Variable password, payload, secret -ErrorAction SilentlyContinue
    }
}
