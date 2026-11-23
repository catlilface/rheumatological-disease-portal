"""Initial schema: stored files, download grants, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    # owner_id is an IAM subject id; no FK, different database. File content
    # lives in SeaweedFS - this table stores metadata and integrity info only.
    """CREATE TABLE stored_files (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    object_key        text NOT NULL UNIQUE,
    owner_id          uuid NOT NULL,
    source_service    text NOT NULL,
    source_reference  text,
    size_bytes        bigint NOT NULL CHECK (size_bytes >= 0),
    checksum_sha256   bytea NOT NULL,
    content_type      text NOT NULL DEFAULT 'application/pdf',
    created_at        timestamptz NOT NULL DEFAULT now()
)""",
    # issued_to is an IAM subject id; no FK, different database.
    """CREATE TABLE download_grants (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stored_file_id  uuid NOT NULL REFERENCES stored_files(id) ON DELETE CASCADE,
    token_hash      bytea NOT NULL UNIQUE,
    issued_to       uuid NOT NULL,
    expires_at      timestamptz NOT NULL,
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in ("inbox_messages", "outbox_events", "download_grants", "stored_files"):
        op.drop_table(table_name)
