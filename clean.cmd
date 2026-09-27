@echo off
setlocal
chcp 65001 >nul
title CR12306 - Clean Test Data
pushd "%~dp0"
echo.
echo CR12306 test data cleanup
echo This removes users, passengers, orders, payments, refunds, waitlists and AI test data.
echo Trains, stations, schedules, fares, seats and administrator accounts are preserved.
echo.
set "CONFIRM="
set /p "CONFIRM=Type CLEAN to continue: "
if /I not "%CONFIRM%"=="CLEAN" goto cancelled
if not exist "%~dp0database\reset_test_data.sql" goto missing_sql
docker version >nul 2>&1
if errorlevel 1 goto no_docker
docker inspect -f "{{.State.Running}}" mysql84 2>nul | findstr /I /X "true" >nul
if errorlevel 1 goto no_mysql
echo.
echo Cleaning database...
docker exec -i -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot CR12306 < "%~dp0database\reset_test_data.sql"
if errorlevel 1 goto failed
echo.
echo Cleanup completed. Current counts:
docker exec -e MYSQL_PWD=123456 mysql84 mysql --default-character-set=utf8mb4 -uroot -D CR12306 --table -e "SELECT (SELECT COUNT(*) FROM app_user) AS users,(SELECT COUNT(*) FROM ticket_order) AS orders,(SELECT COUNT(*) FROM wait_request) AS waitlists;"
echo Seats occupied by the deleted test records have been released.
goto done
:cancelled
echo Cancelled. The database was not changed.
goto done
:missing_sql
echo ERROR: database\reset_test_data.sql was not found.
goto failed_end
:no_docker
echo ERROR: Docker is unavailable. Start Docker Desktop first.
goto failed_end
:no_mysql
echo ERROR: MySQL container mysql84 is not running. Run start.cmd first.
goto failed_end
:failed
echo ERROR: Database cleanup failed. Review the MySQL message above.
:failed_end
popd
pause
exit /b 1
:done
popd
echo.
pause
exit /b 0
