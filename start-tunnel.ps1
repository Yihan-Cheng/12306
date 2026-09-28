param(
    [int]$Port = 8080,
    [switch]$NoRedis,
    [switch]$SkipGraphSync,
    [int]$BookingWorkers = 8,
    [string]$AdminPassword = ''
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repoRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-QuickTunnelUrl([string]$Line) {
    if ($Line -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
        return $Matches[0]
    }
    return $null
}

function Test-ServiceHealthy([int]$TargetPort) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    # /api/health probes three databases via docker exec and can take ~12s; keep a
    # generous timeout and skip any system proxy (e.g. Clash on 127.0.0.1:7897).
    $code = (& curl.exe -s --noproxy '*' -o NUL -w '%{http_code}' --max-time 30 "http://127.0.0.1:$TargetPort/api/health" | Out-String).Trim()
    $ErrorActionPreference = $previous
    return $code -eq '200'
}

Write-Step 'Checking cloudflared'
$cloudflaredCmd = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflaredCmd) {
    throw 'cloudflared was not found. Install it first: winget install --id Cloudflare.cloudflared'
}
$cloudflaredExe = $cloudflaredCmd.Source
Write-Host "    Using: $cloudflaredExe" -ForegroundColor Green

Write-Step 'Checking CR12306 service'
if (Test-ServiceHealthy $Port) {
    Write-Host "    Service already running on port $Port." -ForegroundColor Green
} else {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is occupied by another program. Use -Port 8090 to choose another port."
    }

    Write-Host '    Launching start.ps1 in a new window...' -ForegroundColor Yellow
    $startScript = Join-Path $repoRoot 'start.ps1'
    $argString = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -Port $Port -BookingWorkers $BookingWorkers"
    if ($NoRedis) { $argString += ' -NoRedis' }
    if ($SkipGraphSync) { $argString += ' -SkipGraphSync' }
    if ($AdminPassword) { $argString += " -AdminPassword `"$AdminPassword`"" }
    Start-Process -FilePath 'powershell.exe' -ArgumentList $argString

    Write-Host '    Waiting up to 180 seconds for /api/health ...' -ForegroundColor Yellow
    $ready = $false
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 2
        if (Test-ServiceHealthy $Port) { $ready = $true; break }
    }
    if (-not $ready) {
        throw 'CR12306 service did not become healthy in time. Check the service window for errors.'
    }
    Write-Host '    Service is healthy.' -ForegroundColor Green
}

Write-Step 'Starting Cloudflare Quick Tunnel'
Write-Host "    Local origin: http://127.0.0.1:$Port" -ForegroundColor DarkGray
Write-Host '    Ctrl+C stops the tunnel. The service window stays open; close it to stop everything.' -ForegroundColor DarkGray

$publicUrl = $null
$previousEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $cloudflaredExe tunnel --url "http://127.0.0.1:$Port" --no-autoupdate 2>&1 | ForEach-Object {
        $line = "$_"
        if ($line -match '\bERR\b|failed|error') {
            Write-Host $line -ForegroundColor Red
        } elseif ($line -match 'trycloudflare\.com') {
            Write-Host $line -ForegroundColor Cyan
        } else {
            Write-Host $line -ForegroundColor DarkGray
        }
        if (-not $publicUrl) {
            $found = Get-QuickTunnelUrl $line
            if ($found) {
                $publicUrl = $found
                Write-Host ''
                Write-Host '============================================================' -ForegroundColor Green
                Write-Host '  Quick Tunnel is up. Share this URL with classmates:' -ForegroundColor Green
                Write-Host "  $publicUrl" -ForegroundColor Green
                Write-Host '============================================================' -ForegroundColor Green
                Write-Host ''
                Write-Host "  User site:  $publicUrl/" -ForegroundColor Green
                Write-Host "  Admin site: $publicUrl/admin-login.html  (keep this one to yourself)" -ForegroundColor Yellow
                try {
                    Set-Clipboard -Value $publicUrl
                    Write-Host '  URL copied to clipboard.' -ForegroundColor DarkGray
                } catch {
                    Write-Host '  (clipboard unavailable, copy the URL manually)' -ForegroundColor DarkGray
                }
                Write-Host ''
            }
        }
    }
} finally {
    $ErrorActionPreference = $previousEap
}

Write-Host ''
Write-Host 'Tunnel stopped. Close the service window to shut the demo down.' -ForegroundColor DarkGray
