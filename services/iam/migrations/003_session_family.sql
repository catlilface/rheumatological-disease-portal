-- migrate:up
SET LOCAL search_path = public;
ALTER TABLE auth_sessions
    ADD COLUMN access_token_hash bytea UNIQUE,
    ADD COLUMN access_expires_at timestamptz,
    ADD COLUMN generation bigint NOT NULL DEFAULT 0,
    ADD COLUMN guest_request_id uuid UNIQUE;
-- Credentials from the scaffold are not credentials issued by this authority.
UPDATE auth_sessions SET revoked_at = now() WHERE revoked_at IS NULL;
CREATE TABLE session_refresh_tokens (
    token_hash bytea PRIMARY KEY,
    session_id uuid_v7 NOT NULL REFERENCES auth_sessions ON DELETE CASCADE
);
CREATE UNIQUE INDEX principal_one_role ON principal_roles(principal_id) WHERE revoked_at IS NULL;
ALTER TABLE principals ADD COLUMN blocked_at timestamptz;
ALTER TABLE access_audit ADD COLUMN session_id uuid_v7, ADD COLUMN audience text;

-- migrate:down
SET LOCAL search_path = public;
ALTER TABLE access_audit DROP COLUMN session_id, DROP COLUMN audience;
ALTER TABLE principals DROP COLUMN blocked_at;
DROP INDEX principal_one_role;
DROP TABLE session_refresh_tokens;
ALTER TABLE auth_sessions DROP COLUMN guest_request_id, DROP COLUMN generation,
    DROP COLUMN access_expires_at, DROP COLUMN access_token_hash;
