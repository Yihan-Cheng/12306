# Exercise startup recovery without starting Docker or modifying a database.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$parseErrors = $null
$startup = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repoRoot 'start.ps1'), [ref]$null, [ref]$parseErrors)
if ($parseErrors) { throw ($parseErrors | Out-String) }
$functions = $startup.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $false)
foreach ($function in $functions) { Invoke-Expression $function.Extent.Text }

function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$script:existingRoutines = ''
$script:repairWrites = 0
$script:repairSql = ''
$script:simulateFailure = $false
function Invoke-MySql([string]$Sql, [switch]$Scalar) {
    return $script:existingRoutines
}
function Invoke-MySqlFile([string]$Path) {
    $script:repairWrites++
    $script:repairSql = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    if ($script:simulateFailure) { throw 'Simulated SQL failure' }
    $names = [regex]::Matches($script:repairSql, '(?m)^CREATE (?:FUNCTION|PROCEDURE) (\w+)\(') |
        ForEach-Object { $_.Groups[1].Value }
    $script:existingRoutines = (@($script:existingRoutines) + @($names)) -join "`n"
}

Repair-MissingRoutines -CoreOnly
Assert-True ($script:repairSql -notmatch 'CREATE PROCEDURE sp_(enqueue_booking_request|claim_booking_requests|complete_booking_request)') 'Pre-migration repair must leave V013 routines to their migration.'
$script:existingRoutines = ''
$script:repairWrites = 0
Repair-MissingRoutines
Assert-True ($script:repairWrites -eq 1) 'Empty routine catalog must be repaired.'
$allNames = @($script:existingRoutines -split '\r?\n' | Where-Object { $_ })
Assert-True ($allNames.Count -eq 17) 'Expected all 17 persistent routines.'
Assert-True ($script:repairSql -notmatch '(?m)^(CALL|ALTER TABLE|DROP|CREATE TABLE|CREATE TRIGGER)\b') 'Repair must not replay schema or data changes.'
foreach ($name in @('sp_create_order_hold', 'sp_validate_transfer_candidates')) {
    $matches = [regex]::Matches($script:repairSql, "(?ms)^CREATE PROCEDURE $name\(.*?^END\$\$")
    Assert-True ($matches.Count -eq 1) "Expected one final definition of $name."
}
$v012 = [IO.File]::ReadAllText((Join-Path $repoRoot 'database/migrations/V012__fix_transfer_position_null.sql'))
$latestTransfer = [regex]::Match($v012, '(?ms)^CREATE PROCEDURE sp_validate_transfer_candidates\(.*?^END\$\$').Value
Assert-True ($script:repairSql.Contains($latestTransfer)) 'Transfer repair must use the V012 fix.'
$v005 = [IO.File]::ReadAllText((Join-Path $repoRoot 'database/migrations/V005__seat_position_preferences.sql'))
$latestHold = [regex]::Match($v005, '(?ms)^CREATE PROCEDURE sp_create_order_hold\(.*?^END\$\$').Value
Assert-True ($script:repairSql.Contains($latestHold)) 'Order repair must keep seat preferences from V005.'

Repair-MissingRoutines
Assert-True ($script:repairWrites -eq 1) 'Complete catalog must not be modified.'
$script:existingRoutines = ($allNames | Where-Object { $_ -ne 'sp_claim_booking_requests' }) -join "`r`n"
Repair-MissingRoutines
$partialNames = @([regex]::Matches($script:repairSql, '(?m)^CREATE (?:FUNCTION|PROCEDURE) (\w+)\('))
Assert-True ($partialNames.Count -eq 1 -and $partialNames[0].Groups[1].Value -eq 'sp_claim_booking_requests') 'Partial repair must only recreate the missing routine.'

$script:existingRoutines = ''
$script:simulateFailure = $true
$failed = $false
try { Repair-MissingRoutines } catch {
    Assert-True ($_.Exception.Message -eq 'Simulated SQL failure') 'Unexpected repair error.'
    $failed = $true
}
Assert-True $failed 'SQL errors must stop startup.'
Write-Host 'PASS: empty, complete and partial catalogs; latest definitions; SQL failure propagation.'
