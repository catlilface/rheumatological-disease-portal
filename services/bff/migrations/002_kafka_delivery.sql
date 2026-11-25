-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE kafka_operations (
    id uuid PRIMARY KEY,
    fingerprint bytea NOT NULL,
    outcome jsonb,
    attempts integer NOT NULL DEFAULT 0
);
CREATE TABLE kafka_inbox (
    id uuid PRIMARY KEY,
    fingerprint bytea NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    outcome jsonb
);
CREATE TABLE kafka_versions (
    kind text NOT NULL CHECK (kind IN ('command', 'event')),
    entity_key text NOT NULL,
    version bigint NOT NULL CHECK (version > 0),
    PRIMARY KEY (kind, entity_key)
);
CREATE TABLE kafka_outbox (
    id uuid PRIMARY KEY,
    position bigint GENERATED ALWAYS AS IDENTITY,
    topic text NOT NULL,
    entity_key text NOT NULL,
    payload bytea NOT NULL,
    metadata bytea,
    published_at timestamptz
);
CREATE INDEX kafka_outbox_pending ON kafka_outbox (position) WHERE published_at IS NULL;

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE kafka_outbox, kafka_versions, kafka_inbox, kafka_operations;
