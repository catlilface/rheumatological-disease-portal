-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE principals (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    kind text NOT NULL CHECK (kind IN ('guest','staff')),
    email_hmac bytea UNIQUE,
    password_hash text,
    CHECK ((kind='staff') = (email_hmac IS NOT NULL)),
    CHECK ((kind='staff') = (password_hash IS NOT NULL))
);
CREATE TABLE auth_sessions (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    principal_id uuid_v7 NOT NULL REFERENCES principals ON DELETE CASCADE,
    refresh_token_hash bytea NOT NULL UNIQUE,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL CHECK (expires_at > issued_at),
    revoked_at timestamptz
);
CREATE TABLE roles (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    code text NOT NULL UNIQUE
);
CREATE TABLE principal_roles (
    principal_id uuid_v7 REFERENCES principals ON DELETE CASCADE,
    role_id uuid_v7 REFERENCES roles,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    PRIMARY KEY (principal_id, role_id)
);
CREATE TABLE role_permissions (
    role_id uuid_v7 REFERENCES roles,
    action text NOT NULL,
    resource_type text NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    PRIMARY KEY (role_id, action, resource_type)
);
CREATE TABLE resource_grants (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    principal_id uuid_v7 NOT NULL REFERENCES principals ON DELETE CASCADE,
    resource_type text NOT NULL,
    resource_id uuid_v7 NOT NULL,
    action text NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
-- Historical subject ID, not a reference to a live login. Never store tokens here.
CREATE TABLE access_audit (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    subject_id uuid_v7 NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid_v7 NOT NULL,
    action text NOT NULL,
    allowed boolean NOT NULL,
    reason_code text NOT NULL,
    evaluated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE UPDATE, DELETE ON access_audit FROM mis_iam_app;

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE access_audit, resource_grants, role_permissions, principal_roles, roles, auth_sessions, principals;
