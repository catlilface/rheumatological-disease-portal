"""Initial schema: materials, versions, sources, outbox/inbox."""

from alembic import op
from rheuma_db.outbox import INBOX_MESSAGES_DDL, OUTBOX_EVENTS_DDL

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    """CREATE TYPE material_kind AS ENUM ('article','doctor_route')""",
    """CREATE TYPE review_status AS ENUM ('draft','under_review','approved','published')""",
    """CREATE TABLE materials (
    id          bigserial PRIMARY KEY,
    kind        material_kind NOT NULL,
    slug        text NOT NULL UNIQUE,
    disease_tag text,
    created_at  timestamptz NOT NULL DEFAULT now()
)""",
    # author_id/reviewer_id are IAM subject ids; no FK, different database.
    """CREATE TABLE material_versions (
    id            bigserial PRIMARY KEY,
    material_id   bigint NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    version       bigint NOT NULL,
    title         text NOT NULL,
    summary       text,
    body_markdown text NOT NULL,
    status        review_status NOT NULL DEFAULT 'draft',
    author_id     uuid,
    reviewer_id   uuid,
    published_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (material_id, version)
)""",
    # "At most one published version per material": a partial unique index,
    # not a plain UNIQUE(material_id), since many draft versions may coexist.
    """CREATE UNIQUE INDEX material_versions_one_published_idx
        ON material_versions (material_id) WHERE (status = 'published')""",
    """CREATE TABLE material_sources (
    id                   bigserial PRIMARY KEY,
    material_version_id  bigint NOT NULL REFERENCES material_versions(id) ON DELETE CASCADE,
    title                text NOT NULL,
    url                  text NOT NULL
)""",
    OUTBOX_EVENTS_DDL,
    INBOX_MESSAGES_DDL,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in ("inbox_messages", "outbox_events", "material_sources", "material_versions", "materials"):
        op.drop_table(table_name)
    op.execute("DROP TYPE review_status")
    op.execute("DROP TYPE material_kind")
