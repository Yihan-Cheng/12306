param(
    [int]$Port = 8080,
    [switch]$NoRedis,
    [switch]$SkipGraphSync
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repoRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-DockerReady {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & docker info *> $null
    $ready = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    return $ready
}

function Test-ContainerExists([string]$Name) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & docker inspect $Name *> $null
    $exists = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    return $exists
}

function Ensure-Container([string]$Service, [string]$Name) {
    if (-not (Test-ContainerExists $Name)) {
        Write-Step "Creating container $Name"
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & docker compose up -d $Service
        $code = $LASTEXITCODE
        $ErrorActionPreference = $previous
        if ($code) { throw "Failed to create container $Name" }
    } else {
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        $running = (& docker inspect -f '{{.State.Running}}' $Name 2>$null | Out-String).Trim()
        $ErrorActionPreference = $previous
        if ($running -ne 'true') {
            Write-Step "Starting container $Name"
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            & docker start $Name | Out-Null
            $code = $LASTEXITCODE
            $ErrorActionPreference = $previous
            if ($code) { throw "Failed to start container $Name" }
        }
    }
}

function Invoke-MySql([string]$Sql, [switch]$Scalar) {
    $args = @('exec', '-e', 'MYSQL_PWD=123456', 'mysql84', 'mysql',
              '--default-character-set=utf8mb4', '-uroot', '-D', 'CR12306', '--batch', '--raw')
    if ($Scalar) { $args += @('--skip-column-names') }
    $args += @('-e', $Sql)
    $result = & docker @args 2>$null
    if ($LASTEXITCODE) { throw "MySQL command failed: $Sql" }
    return ($result | Out-String).Trim()
}

function Apply-Migration([string]$Path) {
    Write-Host "    Applying $(Split-Path -Leaf $Path)" -ForegroundColor DarkCyan
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 |
        & docker exec -i -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot CR12306
    if ($LASTEXITCODE) { throw "Migration failed: $Path" }
}

Write-Step 'Checking Docker Desktop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker was not found. Install Docker Desktop first.'
}
if (-not (Test-DockerReady)) {
    $dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw 'Docker Desktop is not running and its default executable was not found.'
    }
    Write-Host '    Starting Docker Desktop in the background...' -ForegroundColor Yellow
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 2
        if (Test-DockerReady) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Docker Desktop was not ready within 80 seconds. Open it manually and retry.' }
}

Ensure-Container 'mysql' 'mysql84'
Ensure-Container 'neo4j' 'neo4j-12306'
if (-not $NoRedis) { Ensure-Container 'redis' 'redis-12306' }

Write-Step 'Waiting for MySQL'
$mysqlReady = $false
for ($i = 0; $i -lt 60; $i++) {
    & docker exec -e MYSQL_PWD=123456 mysql84 mysqladmin ping -h 127.0.0.1 -uroot --silent *> $null
    if ($LASTEXITCODE -eq 0) { $mysqlReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $mysqlReady) { throw 'MySQL was not ready within 120 seconds.' }

Write-Step 'Waiting for Neo4j'
$neo4jReady = $false
for ($i = 0; $i -lt 60; $i++) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & docker exec neo4j-12306 cypher-shell -u neo4j -p 12345678 'RETURN 1' *> $null
    $readyNow = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    if ($readyNow) { $neo4jReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $neo4jReady) { throw 'Neo4j was not ready within 120 seconds.' }

Write-Step 'Checking database migrations'
$hasTicketingSchema = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='seat_type';" -Scalar
if ($hasTicketingSchema -eq '0') {
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'database\migrations') -Filter 'V*.sql' |
        Sort-Object Name | ForEach-Object { Apply-Migration $_.FullName }
} else {
    $hasV013 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='booking_request_buffer';" -Scalar
    if ($hasV013 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V013__admin_auth_and_booking_buffer.sql')
    } else {
        Write-Host '    Database already contains V013.' -ForegroundColor Green
    }
    $hasV014 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='wait_payment';" -Scalar
    if ($hasV014 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V014__wait_prepayment.sql')
    } else {
        Write-Host '    Database already contains V014.' -ForegroundColor Green
    }
}

if (-not $SkipGraphSync) {
    Write-Step 'Checking Neo4j query graph'
    $graphCount = (& docker exec neo4j-12306 cypher-shell -u neo4j -p 12345678 --format plain `
        'MATCH (r:TrainRun) RETURN count(r) AS runs' 2>$null | Select-Object -Last 1).Trim()
    if (-not $graphCount -or $graphCount -eq '0') {
        Write-Host '    Query graph is empty; rebuilding it from MySQL...' -ForegroundColor Yellow
        & (Join-Path $repoRoot 'app\sync_query_graph.ps1')
        if ($LASTEXITCODE) { throw 'Neo4j query graph synchronization failed.' }
    } else {
        Write-Host "    Neo4j contains $graphCount train runs." -ForegroundColor Green
    }
}

Write-Step 'Finding Python 3'
$pythonCandidates = @(
    (Join-Path $env:USERPROFILE '.local\bin\python3.12.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
)
$pythonCommands = @('python', 'python3')
$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $pythonExe = $candidate; break }
}
if (-not $pythonExe) {
    foreach ($command in $pythonCommands) {
        $found = Get-Command $command -ErrorAction SilentlyContinue
        if ($found) { $pythonExe = $found.Source; break }
    }
}
if (-not $pythonExe) {
    throw 'Python 3 was not found. Install Python 3.11+ and enable Add Python to PATH.'
}
Write-Host "    Using: $pythonExe" -ForegroundColor Green

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    try {
        # This endpoint checks three databases. Docker Desktop can need a few
        # seconds to answer immediately after Windows resumes from sleep.
        $healthCode = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 10 "http://127.0.0.1:$Port/api/health" | Out-String).Trim()
        if ($healthCode -eq '200') {
            Write-Host "`nCR12306 is already running: http://127.0.0.1:$Port/" -ForegroundColor Green
            exit 0
        }
    } catch {}
    throw "Port $Port is occupied. Use .\start.ps1 -Port 8090 to choose another port."
}

$env:CR12306_PORT = [string]$Port
$env:CR12306_MYSQL_CONTAINER = 'mysql84'
$env:CR12306_MYSQL_PASSWORD = '123456'
$env:CR12306_NEO4J_CONTAINER = 'neo4j-12306'
$env:CR12306_NEO4J_PASSWORD = '12345678'
$env:CR12306_REDIS_ENABLED = if ($NoRedis) { '0' } else { '1' }
$env:CR12306_REDIS_HOST = '127.0.0.1'
$env:CR12306_REDIS_PORT = '6379'
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'

Write-Host "`nUser site:  http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Admin site: http://127.0.0.1:$Port/admin-login.html" -ForegroundColor Green
Write-Host 'Initial admin: admin / RailFlow@123' -ForegroundColor Yellow
Write-Host 'Press Ctrl+C to stop the service.' -ForegroundColor DarkGray
Write-Step 'Starting CR12306 service'
& $pythonExe (Join-Path $repoRoot 'app\server.py')
