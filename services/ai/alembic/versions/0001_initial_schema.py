"""Initial schema: result/article projections, chunks, embeddings, generations, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    # Local, possibly-lagging copy of a Screening result, updated from events.
    # Not the source of truth and not foreign-keyed to anything outside this database.
    """CREATE TABLE result_projection (
    result_id       uuid NOT NULL,
    version         bigint NOT NULL,
    session_id      uuid NOT NULL,
    subject_id      uuid NOT NULL,
    block_scores    jsonb NOT NULL,
    total_score     integer,
    level           text NOT NULL,
    red_flag_codes  text[] NOT NULL DEFAULT '{}',
    recommendations jsonb NOT NULL DEFAULT '[]',
    disclaimer      text NOT NULL,
    projected_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (result_id, version)
)""",
    # Local copy of a published Content material version, updated from events.
    """CREATE TABLE article_projection (
    article_id    bigint NOT NULL,
    version       bigint NOT NULL,
    slug          text NOT NULL,
    disease_tag   text,
    title         text NOT NULL,
    summary       text,
    status        text NOT NULL,
    published_at  timestamptz,
    projected_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, version)
)""",
    """CREATE TABLE article_chunks (
    id           bigserial PRIMARY KEY,
    article_id   bigint NOT NULL,
    version      bigint NOT NULL,
    chunk_index  integer NOT NULL,
    content      text NOT NULL,
    FOREIGN KEY (article_id, version)
        REFERENCES article_projection (article_id, version) ON DELETE CASCADE,
    UNIQUE (article_id, version, chunk_index)
)""",
    # Plain float array, not pgvector's `vector` type - no extra extension dependency
    # for the MVP; revisit if/when real similarity search is needed.
    """CREATE TABLE chunk_embeddings (
    chunk_id    bigint PRIMARY KEY REFERENCES article_chunks(id) ON DELETE CASCADE,
    model       text NOT NULL,
    embedding   double precision[] NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
)""",
    # subject_id is an IAM subject id; no FK, different database.
    """CREATE TABLE generations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id      uuid NOT NULL,
    result_version bigint NOT NULL,
    subject_id     uuid NOT NULL,
    status         text NOT NULL DEFAULT 'pending',
    answer         text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    completed_at   timestamptz,
    FOREIGN KEY (result_id, result_version) REFERENCES result_projection (result_id, version)
)""",
    """CREATE TABLE generation_sources (
    generation_id  uuid NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    chunk_id       bigint NOT NULL REFERENCES article_chunks(id),
    PRIMARY KEY (generation_id, chunk_id)
)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in (
        "inbox_messages", "outbox_events", "generation_sources", "generations",
        "chunk_embeddings", "article_chunks", "article_projection", "result_projection",
    ):
        op.drop_table(table_name)
