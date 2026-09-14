# 文件编码：UTF-8。零 Python 依赖的 MySQL -> Neo4j 查询投影同步脚本。
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$runExport = @"
SELECT tr.run_id,tr.train_no,DATE_FORMAT(tr.service_date,'%Y-%m-%d'),t.train_type
INTO OUTFILE '/var/lib/mysql-files/query_train_runs.tsv'
FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n'
FROM train_run tr JOIN train t ON t.train_no=tr.train_no;
"@

$callExport = @"
SELECT run_id,station_id,station_order,
       COALESCE(DATE_FORMAT(arrival_at,'%Y-%m-%dT%H:%i:%s'),''),
       COALESCE(DATE_FORMAT(departure_at,'%Y-%m-%dT%H:%i:%s'),'')
INTO OUTFILE '/var/lib/mysql-files/query_calls.tsv'
FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n'
FROM v_train_run_stop ORDER BY run_id,station_order;
"@

docker exec mysql84 rm -f /var/lib/mysql-files/query_train_runs.tsv /var/lib/mysql-files/query_calls.tsv
if ($LASTEXITCODE) { throw '清理 MySQL 临时导出失败' }
docker exec mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 -D CR12306 -e $runExport
if ($LASTEXITCODE) { throw '导出 TrainRun 失败' }
docker exec mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 -D CR12306 -e $callExport
if ($LASTEXITCODE) { throw '导出 CALLS_AT 失败' }

$importDir = Join-Path $PSScriptRoot '.neo4j-import'
New-Item -ItemType Directory -Force -Path $importDir | Out-Null
docker cp mysql84:/var/lib/mysql-files/query_train_runs.tsv (Join-Path $importDir 'query_train_runs.tsv')
if ($LASTEXITCODE) { throw '复制 TrainRun 导出失败' }
docker cp mysql84:/var/lib/mysql-files/query_calls.tsv (Join-Path $importDir 'query_calls.tsv')
if ($LASTEXITCODE) { throw '复制 CALLS_AT 导出失败' }
docker exec neo4j-12306 mkdir -p /var/lib/neo4j/import
if ($LASTEXITCODE) { throw '创建 Neo4j import 目录失败' }
docker cp (Join-Path $importDir 'query_train_runs.tsv') neo4j-12306:/var/lib/neo4j/import/query_train_runs.tsv
if ($LASTEXITCODE) { throw '复制 TrainRun 到 Neo4j 失败' }
docker cp (Join-Path $importDir 'query_calls.tsv') neo4j-12306:/var/lib/neo4j/import/query_calls.tsv
if ($LASTEXITCODE) { throw '复制 CALLS_AT 到 Neo4j 失败' }

$cypher = @"
CREATE CONSTRAINT train_run_id_unique IF NOT EXISTS
FOR (r:TrainRun) REQUIRE r.run_id IS UNIQUE;
CREATE INDEX train_run_service_date IF NOT EXISTS
FOR (r:TrainRun) ON (r.service_date);
MATCH (:TrainRun)-[c:CALLS_AT]->() DELETE c;
MATCH (r:TrainRun) DELETE r;
LOAD CSV FROM 'file:///query_train_runs.tsv' AS row FIELDTERMINATOR '\t'
CREATE (:TrainRun {
  run_id: toInteger(row[0]), train_no: row[1],
  service_date: row[2], train_type: row[3]
});
LOAD CSV FROM 'file:///query_calls.tsv' AS row FIELDTERMINATOR '\t'
MATCH (r:TrainRun {run_id: toInteger(row[0])})
MATCH (s:Station {station_id: toInteger(row[1])})
CREATE (r)-[:CALLS_AT {
  station_order: toInteger(row[2]),
  arrival_at: CASE WHEN row[3] = '' THEN null ELSE row[3] END,
  departure_at: CASE WHEN row[4] = '' THEN null ELSE row[4] END
}]->(s);
"@

docker exec neo4j-12306 cypher-shell -u neo4j -p 12345678 $cypher
if ($LASTEXITCODE) { throw 'Neo4j 查询投影导入失败' }

$validation = @"
MATCH (r:TrainRun) WITH count(r) AS runs
MATCH ()-[c:CALLS_AT]->() RETURN runs,count(c) AS calls;
"@
docker exec neo4j-12306 cypher-shell -u neo4j -p 12345678 --format plain $validation
if ($LASTEXITCODE) { throw 'Neo4j 查询投影校验失败' }
