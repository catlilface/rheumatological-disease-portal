#!/bin/sh
set -eu
for owner in iam screening content reporting files ai ${MIS_BFF_DB:+bff}; do
    echo "Migrating mis_$owner"
    PGPASSWORD=$(cat "/credentials/$owner"); export PGPASSWORD
    export DATABASE_URL="postgres://mis_${owner}_migrator@postgres:5432/mis_${owner}?sslmode=disable&search_path=migration"
    dbmate --no-dump-schema --migration-lock -d /db/common -d "/services/$owner/migrations" migrate --strict
done
