#!/usr/bin/env bash
# Only the fresh, uniquely named test project is ever taken down with -v.
set -euo pipefail
umask 077
mkdir -p .secrets
export MIS_SECRET_DIR
MIS_SECRET_DIR=$(mktemp -d "$PWD/.secrets/test-db.XXXXXXXX")
export COMPOSE_PROJECT_NAME="mis-db-test-$(basename "$MIS_SECRET_DIR" | tr '[:upper:].' '[:lower:]-')"
cleanup() { docker compose down -v && rm -rf "$MIS_SECRET_DIR"; }
trap cleanup EXIT
owners=(iam screening content reporting files ai)
tables=(
  'principals auth_sessions roles principal_roles role_permissions resource_grants access_audit'
  'questionnaire_versions screening_sessions screening_answers screening_results'
  'materials material_versions material_sources' 'report_jobs report_snapshots'
  'stored_files download_grants'
  'result_projection article_projection article_chunks chunk_embeddings generations generation_sources'
)
app() { # $1 = role owner, $2 = target database owner; always real TCP/password auth.
    local owner=$1 target=$2; shift 2
    PGPASSWORD=$(<"$MIS_SECRET_DIR/db/apps/$owner") docker compose exec -T -e PGPASSWORD postgres \
        psql -XqAt -v ON_ERROR_STOP=1 -h postgres -U "mis_${owner}_app" -d "mis_$target" "$@"
}
admin() { docker compose exec -T postgres psql -XqAt -v ON_ERROR_STOP=1 -U postgres -d "$1" -c "$2"; }
# Compare a real domain fixture (including IDs and payload) in each DB, not just a transport marker.
fixtures=(access_audit screening_results material_versions report_snapshots stored_files article_projection)
fixture_rows() { app "$1" "$1" -c "SELECT to_jsonb(t)::text FROM $2 AS t ORDER BY 1"; }
make migrate
expected_dbs=$(printf 'mis_%s\n' "${owners[@]}" | LC_ALL=C sort)
actual_dbs=$(admin postgres "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY datname COLLATE \"C\"")
[[ $actual_dbs == "$expected_dbs" ]] || { echo "Wrong databases: $actual_dbs" >&2; exit 1; }
for i in "${!owners[@]}"; do
    owner=${owners[$i]}
    expected=$(printf '%s\n' ${tables[$i]} inbox_messages outbox_events | LC_ALL=C sort)
    actual=$(admin "mis_$owner" "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename COLLATE \"C\"")
    if [[ $actual != "$expected" ]]; then printf 'Wrong tables in %s:\n%s\n' "$owner" "$actual" >&2; exit 1; fi
    app "$owner" "$owner" <<'SQL'
DO $$ BEGIN
    BEGIN CREATE TABLE public.no_ddl(i int); RAISE EXCEPTION 'Unexpected CREATE'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN CREATE TEMP TABLE no_temp(i int); RAISE EXCEPTION 'Unexpected TEMP'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN DELETE FROM migration.schema_migrations; RAISE EXCEPTION 'Writable history'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
SQL
    for target in "${owners[@]}"; do
        [[ $target != "$owner" ]] || continue
        if err=$(app "$owner" "$target" -c 'SELECT 1' 2>&1); then echo "Unexpected CONNECT $owner -> $target" >&2; exit 1; fi
        grep -F "permission denied for database \"mis_$target\"" <<<"$err" >/dev/null || { echo "$err" >&2; exit 1; }
    done
    app "$owner" "$owner" < "infra/db/tests/$owner.sql"
    rows[$i]=$(fixture_rows "$owner" "${fixtures[$i]}")
    [[ -n ${rows[$i]} ]]
    ids[$i]=$(app "$owner" "$owner" -c "INSERT INTO inbox_messages(message_id,outcome) VALUES (uuidv7(), '\"fixture\"') RETURNING message_id")
    history[$i]=$(admin "mis_$owner" 'SELECT version,xmin FROM migration.schema_migrations ORDER BY version')
    [[ -n ${history[$i]} ]]
done
docker compose up -d --no-deps --force-recreate --wait postgres
make migrate
for i in "${!owners[@]}"; do
    owner=${owners[$i]}
    [[ $(app "$owner" "$owner" -c "SELECT message_id FROM inbox_messages WHERE outcome='\"fixture\"'") == "${ids[$i]}" ]]
    [[ $(fixture_rows "$owner" "${fixtures[$i]}") == "${rows[$i]}" ]] || { echo "Changed fixture in $owner" >&2; exit 1; }
    [[ $(admin "mis_$owner" 'SELECT version,xmin FROM migration.schema_migrations ORDER BY version') == "${history[$i]}" ]] || { echo "Replayed migration in $owner" >&2; exit 1; }
done
echo 'OK: six schemas and app roles, 30 denied connections, invariants and data/history survived recreation'
