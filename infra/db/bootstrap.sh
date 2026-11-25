#!/bin/sh
# Administrative job for the local Compose and Kubernetes stacks. Do not pass the admin secret to dbmate or the apps.
set -eu
export PGHOST=postgres PGUSER=postgres
PGPASSWORD=$(cat /run/secrets/postgres-password); export PGPASSWORD
psql -X -v ON_ERROR_STOP=1 -d postgres <<'SQL'
REVOKE CONNECT, TEMP ON DATABASE postgres, template1 FROM PUBLIC;
-- An existing scaffold volume can also contain the six pre-migration databases.
-- Preserve their data without granting the new service roles access via PUBLIC.
SELECT format('REVOKE CONNECT, TEMP ON DATABASE %I FROM PUBLIC', datname)
FROM pg_database WHERE datname IN ('iam', 'screening', 'content', 'reporting', 'files', 'ai') \gexec
SQL
for owner in iam screening content reporting files ai ${MIS_EXTRA_DB_OWNER:-}; do
    db=mis_$owner; app=${db}_app; migrator=${db}_migrator
    APP_PASSWORD=$(cat "/credentials/apps/$owner"); export APP_PASSWORD
    MIGRATOR_PASSWORD=$(cat "/credentials/migrators/$owner"); export MIGRATOR_PASSWORD
    psql -X -v ON_ERROR_STOP=1 -d postgres -v db="$db" -v app="$app" -v migrator="$migrator" <<'SQL'
\getenv app_password APP_PASSWORD
\getenv migrator_password MIGRATOR_PASSWORD
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', role_name, password)
FROM (VALUES (:'app', :'app_password'), (:'migrator', :'migrator_password')) AS r(role_name, password)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'migrator')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app";
SQL
    psql -X -v ON_ERROR_STOP=1 -d "$db" -v app="$app" -v migrator="$migrator" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app";
CREATE SCHEMA IF NOT EXISTS migration AUTHORIZATION :"migrator";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app";
SQL
done
