#!/usr/bin/env bash
set -euo pipefail

echo ">>> Creating denormalized databases..."

# PostgreSQL — must connect to existing DB (appdb) to run CREATE DATABASE
echo "[1/2] PostgreSQL appdb_denorm..."
docker exec postgresql psql -U admin -d appdb -c "CREATE DATABASE appdb_denorm OWNER admin;" 2>/dev/null || echo "  (database already exists, skipping)"

docker cp sql/postgres-denorm-init.sql postgresql:/tmp/postgres-denorm-init.sql
docker exec postgresql psql -U admin -d appdb_denorm -f /tmp/postgres-denorm-init.sql

# MySQL
echo "[2/2] MySQL appdb_denorm..."
docker exec mysql mysql -u admin -pmysql_secret_123 -e "CREATE DATABASE IF NOT EXISTS appdb_denorm;" 2>/dev/null || true

echo ">>> Denormalized databases ready."