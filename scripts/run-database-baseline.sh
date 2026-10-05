#!/usr/bin/env bash
# Positive control only: native MongoDB 8 replica set and SQL Server Developer.
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
mkdir -p artifacts/database-gate
mongo_image=$(python3 -c 'import json;print(json.load(open("verification/database-gate/baseline-images.json"))[0]["image"])')
sql_image=$(python3 -c 'import json;print(json.load(open("verification/database-gate/baseline-images.json"))[1]["image"])')
cleanup() { docker rm -f d6-mongo d6-sql >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name d6-mongo --platform linux/amd64 -p 127.0.0.1:27017:27017 "$mongo_image" \
  mongod --replSet rs0 --bind_ip_all >/dev/null
# Synthetic CI password; never used by Terraform or Azure.
export D6_SQL_CONNECTION_STRING='Server=127.0.0.1,1433;Database=master;User ID=sa;Password=BaselineOnly-123!;Encrypt=True;TrustServerCertificate=True;Connect Timeout=180'
export D6_MONGO_CONNECTION_STRING='mongodb://127.0.0.1:27017/?directConnection=true'
docker run -d --name d6-sql --platform linux/amd64 -p 127.0.0.1:1433:1433 \
  -e ACCEPT_EULA=Y -e MSSQL_PID=Developer -e MSSQL_SA_PASSWORD='BaselineOnly-123!' "$sql_image" >/dev/null
timeout 90 bash -c 'until docker exec d6-mongo mongosh --quiet --eval "db.adminCommand({ping:1})" >/dev/null 2>&1; do sleep 2; done'
docker exec d6-mongo mongosh --quiet --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"localhost:27017"}]})' >/dev/null
timeout 90 bash -c 'until docker exec d6-mongo mongosh --quiet --eval "if(!db.hello().isWritablePrimary)quit(1)" >/dev/null 2>&1; do sleep 2; done'
timeout 180 bash -c 'until docker exec d6-sql /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "BaselineOnly-123!" -C -Q "SELECT 1" >/dev/null 2>&1; do sleep 2; done'
dotnet restore verification/database-gate/dotnet --locked-mode --verbosity quiet
dotnet build verification/database-gate/dotnet --no-restore --verbosity quiet
status=0
timeout 600 dotnet run --project verification/database-gate/dotnet --no-build --no-restore -- \
  native-baseline artifacts/database-gate/dotnet-baseline.json || status=1
uv sync --frozen --project artifacts/database-gate/payments
timeout 600 uv run --frozen --project artifacts/database-gate/payments python \
  verification/database-gate/payments-gate.py native-baseline artifacts/database-gate/payments \
  artifacts/database-gate/payments-baseline.json || status=1
python3 scripts/report-database-gate.py native-baseline \
  artifacts/database-gate/dotnet-baseline.json artifacts/database-gate/payments-baseline.json || status=1
exit "$status"
