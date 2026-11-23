"""Initial schema: report jobs, snapshots, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    """CREATE TYPE report_status AS ENUM ('pending','generating','ready','failed')""",
    # result_id/file_id are Screening/Files ids; no FK, different databases.
    # operation_id UNIQUE: one PDF job per operation, safe to retry/dedupe on.
    """CREATE TABLE report_jobs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id      uuid NOT NULL UNIQUE,
    result_id         uuid NOT NULL,
    result_version    bigint NOT NULL,
    template_version  text NOT NULL,
    locale            text NOT NULL,
    status            report_status NOT NULL DEFAULT 'pending',
    file_id           uuid,
    failure_code      text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    generated_at      timestamptz,
    version           bigint NOT NULL DEFAULT 1
)""",
    # One snapshot per job: encrypted inputs + template version for a reproducible re-render.
    """CREATE TABLE report_snapshots (
    id                bigserial PRIMARY KEY,
    report_job_id     uuid NOT NULL UNIQUE REFERENCES report_jobs(id) ON DELETE CASCADE,
    template_version  text NOT NULL,
    encrypted_input   bytea NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in ("inbox_messages", "outbox_events", "report_snapshots", "report_jobs"):
        op.drop_table(table_name)
    op.execute("DROP TYPE report_status")
