param([switch]$Yes)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resetSql = Join-Path $repoRoot 'database\reset_test_data.sql'

Write-Host ''
Write-Host 'CR12306 测试数据清理' -ForegroundColor Cyan
Write-Host '将删除：普通用户、乘车人、订单、支付、退票、候补和 AI 压测记录。' -ForegroundColor Yellow
Write-Host '将保留：管理员、车次、站点、时刻、票价和席位配置。'

if (-not $Yes) {
    $answer = Read-Host '输入 CLEAN 确认清理'
    if ($answer -cne 'CLEAN') {
        Write-Host '已取消，数据库未修改。' -ForegroundColor DarkGray
        exit 0
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 Docker，请先安装并启动 Docker Desktop。'
}
if (-not (Test-Path -LiteralPath $resetSql)) {
    throw "找不到清理脚本：$resetSql"
}

$running = (& docker inspect -f '{{.State.Running}}' mysql84 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw 'MySQL 容器 mysql84 未运行，请先运行 start.cmd。'
}

Write-Host '正在清理…' -ForegroundColor Cyan
Get-Content -LiteralPath $resetSql -Raw -Encoding UTF8 |
    & docker exec -i -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot CR12306
if ($LASTEXITCODE -ne 0) { throw '数据清理失败。' }

$counts = & docker exec -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot -D CR12306 `
    --batch --raw --skip-column-names -e "SELECT CONCAT('users=',COUNT(*)) FROM app_user UNION ALL SELECT CONCAT('orders=',COUNT(*)) FROM ticket_order UNION ALL SELECT CONCAT('waits=',COUNT(*)) FROM wait_request;"
if ($LASTEXITCODE -ne 0) { throw '清理完成，但验证失败。' }

Write-Host '清理完成：' -ForegroundColor Green
$counts | ForEach-Object { Write-Host "  $_" }
Write-Host '已占用席位也已全部释放。正在运行的管理端会话需要重新登录。' -ForegroundColor Green
