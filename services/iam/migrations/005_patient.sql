-- migrate:up
SET LOCAL search_path = public;
ALTER TABLE principals ADD COLUMN consent_version text;
ALTER TABLE auth_sessions ADD COLUMN registration_request_id uuid UNIQUE;
CREATE TABLE admin_bootstrap (singleton boolean PRIMARY KEY CHECK (singleton));

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE admin_bootstrap;
ALTER TABLE auth_sessions DROP COLUMN registration_request_id;
ALTER TABLE principals DROP COLUMN consent_version;
