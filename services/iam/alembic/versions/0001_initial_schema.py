"""Initial schema: principals, sessions, roles/permissions/grants, access audit, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    """CREATE TYPE principal_kind AS ENUM ('guest','employee')""",
    """CREATE TABLE principals (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          principal_kind NOT NULL,
    email_hash    bytea UNIQUE,
    password_hash text,
    display_name  text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT principal_kind_email_hash CHECK (
        (kind = 'employee' AND email_hash IS NOT NULL) OR (kind = 'guest' AND email_hash IS NULL)
    )
)""",
    """CREATE TABLE auth_sessions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id       uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    session_token_hash bytea NOT NULL UNIQUE,
    issued_at          timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    revoked_at         timestamptz
)""",
    """CREATE TABLE roles (
    code        text PRIMARY KEY,
    description text NOT NULL DEFAULT ''
)""",
    """CREATE TABLE principal_roles (
    principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    role_code    text NOT NULL REFERENCES roles(code) ON DELETE RESTRICT,
    granted_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz,
    revoked_at   timestamptz,
    PRIMARY KEY (principal_id, role_code)
)""",
    """CREATE TABLE role_permissions (
    role_code  text NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission text NOT NULL,
    PRIMARY KEY (role_code, permission)
)""",
    """CREATE TABLE resource_grants (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id  uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    resource_type text NOT NULL,
    resource_id   text NOT NULL,
    permission    text NOT NULL,
    granted_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz,
    revoked_at    timestamptz,
    UNIQUE (principal_id, resource_type, resource_id, permission)
)""",
    # No FK to principals: a decision log must survive account deletion.
    """CREATE TABLE access_audit (
    id                   bigserial PRIMARY KEY,
    actor_principal_id   uuid NOT NULL,
    subject_principal_id uuid NOT NULL,
    action               text NOT NULL,
    resource_type        text NOT NULL,
    resource_id          text,
    decision             text NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE INDEX access_audit_subject_principal_id_created_at_idx
        ON access_audit (subject_principal_id, created_at)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in (
        "inbox_messages", "outbox_events", "access_audit", "resource_grants",
        "role_permissions", "principal_roles", "roles", "auth_sessions", "principals",
    ):
        op.drop_table(table_name)
    op.execute("DROP TYPE principal_kind")
