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

function Invoke-MySqlFile([string]$Path) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'docker'
    $psi.Arguments = 'exec -i -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot CR12306'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    try {
        # Drain both output streams before writing to prevent pipe deadlocks.
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()
        $bytes = [IO.File]::ReadAllBytes($Path)
        $proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
        $proc.StandardInput.Close()
        $proc.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($stdout.Trim()) { Write-Host $stdout -ForegroundColor DarkGray }
        if ($stderr.Trim()) { Write-Host $stderr -ForegroundColor DarkYellow }
        if ($proc.ExitCode) { throw "MySQL file execution failed: $Path" }
    } finally {
        $proc.Dispose()
    }
}

function Apply-Migration([string]$Path) {
    Write-Host "    Applying $(Split-Path -Leaf $Path)" -ForegroundColor DarkCyan
    # Preserve Chinese SQL literals on Windows PowerShell by sending UTF-8 bytes.
    Invoke-MySqlFile $Path
}

function Repair-MissingRoutines([switch]$CoreOnly) {
    # Extract only persistent routine definitions; never replay data generation.
    $definitions = [ordered]@{}
    $versions = @('V004', 'V005', 'V006', 'V009', 'V010', 'V011', 'V012')
    if (-not $CoreOnly) { $versions += 'V013' }
    foreach ($version in $versions) {
        $files = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'database\migrations') -Filter "${version}__*.sql")
        if ($files.Count -ne 1) { throw "Expected one migration for $version." }
        $sql = [IO.File]::ReadAllText($files[0].FullName, [Text.Encoding]::UTF8)
        $matches = [regex]::Matches($sql, '(?ms)^CREATE (?:FUNCTION|PROCEDURE) (\w+)\(.*?^END\$\$')
        if ($matches.Count -eq 0) { throw "No routine definitions found in $version." }
        foreach ($match in $matches) { $definitions[$match.Groups[1].Value] = $match.Value }
    }
    $existing = Invoke-MySql "SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='CR12306';" -Scalar
    $existingNames = @($existing -split '\r?\n' | ForEach-Object { $_.Trim() })
    $missing = @($definitions.Keys | Where-Object { $_ -notin $existingNames })
    if ($missing.Count -eq 0) {
        Write-Host '    Application routines are complete.' -ForegroundColor Green
        return
    }
    Write-Host "    Repairing missing routines: $($missing -join ', ')" -ForegroundColor Yellow
    $repairSql = 'SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;' + "`nUSE CR12306;`n" + 'DELIMITER $$' + "`n"
    foreach ($name in $missing) { $repairSql += $definitions[$name] + "`n" }
    $repairSql += "DELIMITER ;`n"
    $repairPath = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($repairPath, $repairSql, [Text.UTF8Encoding]::new($false))
        Invoke-MySqlFile $repairPath
        $repaired = Invoke-MySql "SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='CR12306';" -Scalar
        $repairedNames = @($repaired -split '\r?\n' | ForEach-Object { $_.Trim() })
        $remaining = @($missing | Where-Object { $_ -notin $repairedNames })
        if ($remaining.Count) { throw "Routine repair incomplete: $($remaining -join ', ')" }
    } finally {
        [IO.File]::Delete($repairPath)
    }
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
$databaseChanged = $false
$hasTicketingSchema = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='seat_type';" -Scalar
if ($hasTicketingSchema -eq '0') {
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'database\migrations') -Filter 'V*.sql' |
        Sort-Object Name | ForEach-Object { Apply-Migration $_.FullName }
    $databaseChanged = $true
} else {
    # Later migrations can call these routines when upgrading a restored dump.
    Repair-MissingRoutines -CoreOnly
    $hasV013 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='booking_request_buffer';" -Scalar
    if ($hasV013 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V013__admin_auth_and_booking_buffer.sql')
    } else {
        Write-Host '    Database already contains V013.' -ForegroundColor Green
    }
    $hasV014 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='CR12306' AND table_name='wait_payment';" -Scalar
    if ($hasV014 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V014__wait_prepayment.sql')
        $databaseChanged = $true
    } else {
        Write-Host '    Database already contains V014.' -ForegroundColor Green
    }
    $hasV015 = Invoke-MySql "SELECT COUNT(*) FROM train_run tr WHERE tr.train_no='G8359' AND tr.stop_count=14 AND tr.segment_count=13 AND (SELECT COUNT(*) FROM train_station ts WHERE ts.train_no='G8359')=14 AND EXISTS (SELECT 1 FROM train_station ts JOIN station s ON s.station_id=ts.station_id WHERE ts.train_no='G8359' AND ts.station_order=14 AND s.station_name='义乌');" -Scalar
    if ($hasV015 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V015__add_g8359_extra_service.sql')
        $databaseChanged = $true
    } else {
        Write-Host '    Database already contains V015 (G8359).' -ForegroundColor Green
    }
    $hasV016 = Invoke-MySql "SELECT COUNT(*) FROM (SELECT COUNT(DISTINCT service_date) date_count,MIN(service_date) service_date,COUNT(*) run_count,SUM(train_no='G8359') g8359_count FROM train_run) x WHERE x.date_count=1 AND x.service_date IN ('2026-10-07','2026-10-14') AND x.run_count>0 AND x.g8359_count=1;" -Scalar
    if ($hasV016 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V016__unify_demo_service_date.sql')
        $databaseChanged = $true
    } else {
        Write-Host '    Database already contains V016 (unified demo date).' -ForegroundColor Green
    }
    $hasV017 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='CR12306' AND trigger_name='trg_order_item_passenger_itinerary_guard' AND action_statement LIKE '%STRAIGHT_JOIN train_run%';" -Scalar
    if ($hasV017 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V017__fast_itinerary_conflict_guard.sql')
    } else {
        Write-Host '    Database already contains V017 (fast itinerary conflict guard).' -ForegroundColor Green
    }
    $hasV018 = Invoke-MySql "SELECT COUNT(*) FROM information_schema.views WHERE table_schema='CR12306' AND table_name='v_order_detail' AND view_definition LIKE '%straight_join%';" -Scalar
    if ($hasV018 -eq '0') {
        Apply-Migration (Join-Path $repoRoot 'database\migrations\V018__fast_order_detail_view.sql')
    } else {
        Write-Host '    Database already contains V018 (fast order detail view).' -ForegroundColor Green
    }
}

$hasV019 = Invoke-MySql "SELECT COUNT(*) FROM (SELECT COUNT(*) run_count,SUM(service_date<>'2026-10-14' OR run_status<>'ON_SALE' OR sale_start_at<>'2026-09-29 00:00:00' OR sale_end_at<>'2026-10-16 00:00:00') outdated_count FROM train_run) x WHERE x.run_count>0 AND x.outdated_count=0;" -Scalar
if ($hasV019 -eq '0') {
    Apply-Migration (Join-Path $repoRoot 'database\migrations\V019__move_demo_service_date_to_oct14.sql')
    $databaseChanged = $true
} else {
    Write-Host '    Database already contains V019 (October 14 demo date).' -ForegroundColor Green
}

Repair-MissingRoutines

# Idempotent views and role grants also repair an interrupted V020 installation.
Apply-Migration (Join-Path $repoRoot 'database\migrations\V020__operations_reporting.sql')
Apply-Migration (Join-Path $repoRoot 'database\migrations\V021__anomaly_evidence.sql')

if (-not $SkipGraphSync) {
    Write-Step 'Checking Neo4j query graph'
    $graphCount = (& docker exec neo4j-12306 cypher-shell -u neo4j -p 12345678 --format plain `
        'MATCH (r:TrainRun) RETURN count(r) AS runs' 2>$null | Select-Object -Last 1).Trim()
    if ($databaseChanged -or -not $graphCount -or $graphCount -eq '0') {
        Write-Host '    Rebuilding the query graph from current MySQL data...' -ForegroundColor Yellow
        & (Join-Path $repoRoot 'app\sync_query_graph.ps1')
        if ($LASTEXITCODE) { throw 'Neo4j query graph synchronization failed.' }
    } else {
        Write-Host "    Neo4j contains $graphCount train runs." -ForegroundColor Green
    }
}

Write-Step 'Finding Python 3'
$pythonCandidates = @(
    $(if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX 'python.exe' }),
    'D:\anaconda\python.exe',
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
        # Database probes can be slow after resume; bypass the local HTTP proxy.
        $healthCode = (& curl.exe -s --noproxy '*' -o NUL -w '%{http_code}' --max-time 30 "http://127.0.0.1:$Port/api/health" | Out-String).Trim()
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
$env:CR12306_BOOKING_WORKERS = [string]([Math]::Max(1, [Math]::Min(8, $BookingWorkers)))
if ($AdminPassword) { $env:CR12306_ADMIN_PASSWORD = $AdminPassword }
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'

# Each running web port uses a separate reader. Its generated password lives
# only in the server environment. Deployments may supply a pre-provisioned pair.
if (-not $env:CR12306_OPS_DB_USER -and -not $env:CR12306_OPS_DB_PASSWORD) {
    $reader = "railflow_ops_$Port"
    $secret = [guid]::NewGuid().ToString('N')
    try {
        Invoke-MySql "CREATE USER IF NOT EXISTS '$reader'@'%' IDENTIFIED BY '$secret'; ALTER USER '$reader'@'%' IDENTIFIED BY '$secret'; GRANT 'railflow_ops_reports' TO '$reader'@'%'; SET DEFAULT ROLE 'railflow_ops_reports' TO '$reader'@'%';" | Out-Null
    } catch { throw 'Failed to provision the read-only operations user.' }
    $env:CR12306_OPS_DB_USER = $reader
    $env:CR12306_OPS_DB_PASSWORD = $secret
} elseif (-not $env:CR12306_OPS_DB_USER -or -not $env:CR12306_OPS_DB_PASSWORD) {
    throw 'Set both CR12306_OPS_DB_USER and CR12306_OPS_DB_PASSWORD.'
}

Write-Host "`nUser site:  http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Admin site: http://127.0.0.1:$Port/admin-login.html" -ForegroundColor Green
if ($AdminPassword) {
    Write-Host 'Initial admin: admin / (the -AdminPassword you passed)' -ForegroundColor Yellow
} else {
    Write-Host 'Initial admin: admin / RailFlow@123' -ForegroundColor Yellow
}
Write-Host 'Press Ctrl+C to stop the service.' -ForegroundColor DarkGray
Write-Step 'Starting CR12306 service'
& $pythonExe (Join-Path $repoRoot 'app\server.py')
