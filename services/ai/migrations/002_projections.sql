-- migrate:up
SET LOCAL search_path = public;
-- The source UUID and version survive a tombstone; the projected payload does not.
CREATE TABLE result_projection (
    result_id uuid_v7 PRIMARY KEY,
    version bigint NOT NULL CHECK (version > 0),
    deleted boolean NOT NULL DEFAULT false,
    snapshot jsonb,
    CHECK (deleted = (snapshot IS NULL))
);
CREATE TABLE article_projection (
    article_id uuid_v7 PRIMARY KEY,
    version bigint NOT NULL CHECK (version > 0),
    published boolean NOT NULL,
    deleted boolean NOT NULL DEFAULT false,
    snapshot jsonb,
    CHECK (deleted = (snapshot IS NULL)), CHECK (NOT (deleted AND published))
);
CREATE FUNCTION newer_projection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.version <= OLD.version THEN RAISE EXCEPTION 'Projection version must advance' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER newer_result BEFORE UPDATE ON result_projection FOR EACH ROW EXECUTE FUNCTION newer_projection();
CREATE TRIGGER newer_article BEFORE UPDATE ON article_projection FOR EACH ROW EXECUTE FUNCTION newer_projection();
REVOKE DELETE ON article_projection, result_projection FROM mis_ai_app;
CREATE TABLE article_chunks (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    article_id uuid_v7 NOT NULL REFERENCES article_projection,
    article_version bigint NOT NULL CHECK (article_version > 0),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    body text NOT NULL,
    UNIQUE (article_id, article_version, ordinal)
);
CREATE TABLE chunk_embeddings (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    chunk_id uuid_v7 NOT NULL REFERENCES article_chunks ON DELETE CASCADE,
    model_version text NOT NULL,
    qdrant_point_id uuid_v7 NOT NULL UNIQUE,
    UNIQUE (chunk_id, model_version)
);
CREATE TABLE generations (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    result_id uuid_v7 NOT NULL REFERENCES result_projection,
    result_version bigint NOT NULL CHECK (result_version > 0),
    owner_id uuid_v7 NOT NULL,
    status text NOT NULL CHECK (status IN ('pending','ready','failed')),
    explanation text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE generation_sources (
    generation_id uuid_v7 REFERENCES generations ON DELETE CASCADE,
    chunk_id uuid_v7 REFERENCES article_chunks,
    PRIMARY KEY (generation_id, chunk_id)
);

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE generation_sources, generations, chunk_embeddings, article_chunks, article_projection, result_projection;
DROP FUNCTION newer_projection();
