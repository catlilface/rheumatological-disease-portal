#!/bin/sh
set -eu

if [ "${1:-}" = "--docker" ]; then
    postgres_container=${2:?PostgreSQL container ID is required}
    credentials=${MIS_SECRET_DIR:-.secrets}/db/migrators
    case $credentials in
        /*) ;;
        *) credentials=$PWD/$credentials ;;
    esac

    set -- --rm --network "container:$postgres_container" \
        -e DBMATE_HOST=127.0.0.1 -e MIS_BFF_DB \
        -v "$PWD/infra/db:/db:ro" -v "$credentials:/credentials:ro"

    for owner in iam screening content reporting files ai ${MIS_BFF_DB:+bff}; do
        set -- "$@" -v "$PWD/services/$owner/migrations:/services/$owner/migrations:ro"
    done

    exec docker run "$@" --entrypoint sh ghcr.io/amacneil/dbmate:2.38.2 /db/migrate.sh
fi

for owner in iam screening content reporting files ai ${MIS_BFF_DB:+bff}; do
    echo "Migrating mis_$owner"
    PGPASSWORD=$(cat "/credentials/$owner"); export PGPASSWORD
    export DATABASE_URL="postgres://mis_${owner}_migrator@${DBMATE_HOST:-postgres}:5432/mis_${owner}?sslmode=disable&search_path=migration"
    dbmate --no-dump-schema --migration-lock -d /db/common -d "/services/$owner/migrations" migrate --strict
done
