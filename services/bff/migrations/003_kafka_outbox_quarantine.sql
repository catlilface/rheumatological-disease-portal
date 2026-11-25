-- migrate:up
ALTER TABLE public.kafka_outbox
    ADD COLUMN quarantined_at timestamptz,
    ADD COLUMN publish_error integer,
    ADD CONSTRAINT kafka_outbox_quarantine_state CHECK (
        (quarantined_at IS NULL AND publish_error IS NULL)
        OR (quarantined_at IS NOT NULL AND publish_error IS NOT NULL AND published_at IS NULL)
    );
CREATE INDEX kafka_outbox_quarantined_key
    ON public.kafka_outbox (topic, entity_key, position) WHERE quarantined_at IS NOT NULL;

-- migrate:down
DROP INDEX public.kafka_outbox_quarantined_key;
ALTER TABLE public.kafka_outbox
    DROP CONSTRAINT kafka_outbox_quarantine_state,
    DROP COLUMN publish_error,
    DROP COLUMN quarantined_at;
