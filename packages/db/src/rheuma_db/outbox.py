"""Local inbox/outbox tables, identical in shape across every service's own DB.

Each service owns its own physical copy of these tables - there is no shared
outbox table across services. Migrations should use the frozen DDL constants
below (see `rheuma_db.outbox.OUTBOX_EVENTS_DDL`); the `register_*_model`
functions provide the matching SQLAlchemy mapping for schema-contract tests.
"""

from sqlalchemy import BigInteger, Column, DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

OUTBOX_EVENTS_DDL = """
CREATE TABLE outbox_events (
    id             bigserial PRIMARY KEY,
    event_id       uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    aggregate_type text NOT NULL,
    aggregate_id   text NOT NULL,
    event_type     text NOT NULL,
    payload        jsonb NOT NULL,
    occurred_at    timestamptz NOT NULL DEFAULT now(),
    published_at   timestamptz
)
""".strip()

INBOX_MESSAGES_DDL = """
CREATE TABLE inbox_messages (
    id           bigserial PRIMARY KEY,
    message_id   uuid NOT NULL UNIQUE,
    message_type text NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    status       text NOT NULL DEFAULT 'pending'
)
""".strip()


def register_outbox_model(base: type) -> type:
    """Bind an OutboxEvent model to the caller's own declarative Base."""

    class OutboxEvent(base):
        __tablename__ = "outbox_events"

        id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
        event_id = Column(
            UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()"),
        )
        aggregate_type = Column(Text(), nullable=False)
        aggregate_id = Column(Text(), nullable=False)
        event_type = Column(Text(), nullable=False)
        payload = Column(JSONB(), nullable=False)
        occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
        published_at = Column(DateTime(timezone=True), nullable=True)

    return OutboxEvent


def register_inbox_model(base: type) -> type:
    """Bind an InboxMessage model to the caller's own declarative Base."""

    class InboxMessage(base):
        __tablename__ = "inbox_messages"

        id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
        message_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
        message_type = Column(Text(), nullable=False)
        received_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
        processed_at = Column(DateTime(timezone=True), nullable=True)
        status = Column(Text(), nullable=False, server_default=text("'pending'"))

    return InboxMessage
