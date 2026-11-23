"""Initial schema: questionnaire versions, sessions, answers, results, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    """CREATE TYPE session_status  AS ENUM ('in_progress','completed','abandoned')""",
    """CREATE TYPE screening_level AS ENUM ('low','medium','high','red_flag')""",
    # Frozen snapshot of the questionnaire JSON contract (ТЗ Дополнение №1, section 3)
    # for a given (survey_id, weights_version); never a second set of rules.
    """CREATE TABLE questionnaire_versions (
    survey_id          text NOT NULL,
    weights_version    text NOT NULL,
    definition         jsonb NOT NULL,
    disclaimer         text NOT NULL,
    disclaimer_version text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (survey_id, weights_version)
)""",
    # owner_id is an IAM subject id (including guests); no FK, different database.
    """CREATE TABLE screening_sessions (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_token            uuid NOT NULL UNIQUE,
    owner_id                 uuid,
    survey_id                text NOT NULL,
    weights_version          text NOT NULL,
    status                   session_status NOT NULL DEFAULT 'in_progress',
    interrupted_by_red_flag  boolean NOT NULL DEFAULT false,
    started_at               timestamptz NOT NULL DEFAULT now(),
    completed_at             timestamptz,
    version                  bigint NOT NULL DEFAULT 1,
    FOREIGN KEY (survey_id, weights_version)
        REFERENCES questionnaire_versions (survey_id, weights_version)
)""",
    # One answer per (session, question): a later answer overwrites, never duplicates.
    """CREATE TABLE screening_answers (
    id             bigserial PRIMARY KEY,
    session_id     uuid NOT NULL REFERENCES screening_sessions(id) ON DELETE CASCADE,
    question_code  varchar(8) NOT NULL,
    value          jsonb NOT NULL,
    weighted_score integer NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, question_code)
)""",
    # session_id UNIQUE enforces "exactly one result per completed session"; the
    # application never updates a row here once written (immutability by convention).
    """CREATE TABLE screening_results (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       uuid NOT NULL UNIQUE REFERENCES screening_sessions(id),
    version          bigint NOT NULL DEFAULT 1,
    block_scores     jsonb NOT NULL,
    total_score      integer,
    scoring_complete boolean NOT NULL DEFAULT false,
    red_flag_codes   text[] NOT NULL DEFAULT '{}',
    level            screening_level NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in (
        "inbox_messages", "outbox_events", "screening_results",
        "screening_answers", "screening_sessions", "questionnaire_versions",
    ):
        op.drop_table(table_name)
    op.execute("DROP TYPE screening_level")
    op.execute("DROP TYPE session_status")
