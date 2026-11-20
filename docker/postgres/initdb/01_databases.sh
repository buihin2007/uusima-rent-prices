#!/bin/bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<EOSQL
CREATE USER airflow WITH PASSWORD '${AIRFLOW_DB_PASSWORD}';
CREATE DATABASE airflow OWNER airflow;

CREATE USER iceberg WITH PASSWORD '${CATALOG_DB_PASSWORD}';
CREATE DATABASE iceberg_catalog OWNER iceberg;

CREATE USER housing WITH PASSWORD '${HOUSING_DB_PASSWORD}';
CREATE DATABASE housing OWNER housing;
EOSQL