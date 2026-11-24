-- migrate:up
SET LOCAL search_path = public;
CREATE DOMAIN uuid_v7 AS uuid CHECK (VALUE IS NULL OR uuid_extract_version(VALUE) IS NOT DISTINCT FROM 7);

-- Store the contract ID, not a new local ID, so a redelivery collides.
CREATE TABLE inbox_messages (
    message_id uuid_v7 PRIMARY KEY,
    operation_id uuid_v7,
    processed_at timestamptz NOT NULL DEFAULT now(),
    outcome jsonb
);
CREATE TABLE outbox_events (
    event_id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    source text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid_v7 NOT NULL,
    entity_version bigint NOT NULL CHECK (entity_version > 0),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    operation_id uuid_v7 NOT NULL,
    causation_id uuid_v7 NOT NULL,
    correlation_id uuid_v7 NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload bytea NOT NULL, -- serialized MIS-22 event
    published_at timestamptz
);
CREATE INDEX outbox_pending ON outbox_events (occurred_at) WHERE published_at IS NULL;

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE outbox_events, inbox_messages;
DROP DOMAIN uuid_v7;
