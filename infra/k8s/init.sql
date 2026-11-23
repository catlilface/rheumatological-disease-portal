CREATE DATABASE content;
CREATE DATABASE screening;
CREATE DATABASE reporting;
CREATE DATABASE files;
CREATE DATABASE iam;
CREATE DATABASE ai;

-- One shared password for every least-privilege app role: this is a
-- synthetic-data dev stand (see infra/README.md), and the isolation
-- property below comes from per-service role *identity* and grants, not
-- from each role holding a unique secret.
\set service_password `tr -d '\n' < /run/secrets/service-db-password`

-- Migrations run as the postgres superuser (see packages/service-runtime).
-- Each app_<service> role can read/write only its own database: it cannot
-- create tables there (Postgres 15+ already denies CREATE on schema public
-- to non-owners by default) and cannot even CONNECT to the other five.
CREATE ROLE app_iam       LOGIN PASSWORD :'service_password';
CREATE ROLE app_screening LOGIN PASSWORD :'service_password';
CREATE ROLE app_content   LOGIN PASSWORD :'service_password';
CREATE ROLE app_reporting LOGIN PASSWORD :'service_password';
CREATE ROLE app_files     LOGIN PASSWORD :'service_password';
CREATE ROLE app_ai        LOGIN PASSWORD :'service_password';

-- `\set ... \`shell\`` does not fail the script if the shell command errors
-- (e.g. permission denied reading the secret) - it just leaves the variable
-- empty, and PASSWORD '' silently stores no password at all. Check for that
-- directly instead of trusting the shell exit code: ON_ERROR_STOP=1 turns
-- this RAISE EXCEPTION into a fatal, non-zero-exit initialization failure.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_authid
        WHERE rolname IN ('app_iam', 'app_screening', 'app_content', 'app_reporting', 'app_files', 'app_ai')
          AND rolpassword IS NULL
    ) THEN
        RAISE EXCEPTION
            'service-db-password was not read (check it exists and is readable by the postgres OS user, uid 70)';
    END IF;
END $$;

REVOKE CONNECT ON DATABASE iam FROM PUBLIC;
REVOKE CONNECT ON DATABASE screening FROM PUBLIC;
REVOKE CONNECT ON DATABASE content FROM PUBLIC;
REVOKE CONNECT ON DATABASE reporting FROM PUBLIC;
REVOKE CONNECT ON DATABASE files FROM PUBLIC;
REVOKE CONNECT ON DATABASE ai FROM PUBLIC;

GRANT CONNECT ON DATABASE iam TO app_iam;
GRANT CONNECT ON DATABASE screening TO app_screening;
GRANT CONNECT ON DATABASE content TO app_content;
GRANT CONNECT ON DATABASE reporting TO app_reporting;
GRANT CONNECT ON DATABASE files TO app_files;
GRANT CONNECT ON DATABASE ai TO app_ai;

-- Grant DML on whatever the superuser migrates into each database, now and
-- in the future (ALTER DEFAULT PRIVILEGES only covers objects created after
-- this point, by this same role, in this database).
\c iam
GRANT USAGE ON SCHEMA public TO app_iam;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_iam;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_iam;

\c screening
GRANT USAGE ON SCHEMA public TO app_screening;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_screening;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_screening;

\c content
GRANT USAGE ON SCHEMA public TO app_content;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_content;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_content;

\c reporting
GRANT USAGE ON SCHEMA public TO app_reporting;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_reporting;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_reporting;

\c files
GRANT USAGE ON SCHEMA public TO app_files;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_files;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_files;

\c ai
GRANT USAGE ON SCHEMA public TO app_ai;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_ai;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_ai;
