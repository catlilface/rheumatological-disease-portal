-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE stored_files (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    object_key text NOT NULL UNIQUE,
    owner_id uuid_v7 NOT NULL,
    report_id uuid_v7 NOT NULL,
    source_result_id uuid_v7 NOT NULL,
    source_result_version bigint NOT NULL CHECK (source_result_version > 0),
    filename text NOT NULL,
    media_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    sha256 bytea NOT NULL CHECK (octet_length(sha256)=32),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE download_grants (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    file_id uuid_v7 NOT NULL REFERENCES stored_files ON DELETE CASCADE,
    subject_id uuid_v7 NOT NULL,
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash)=32),
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL CHECK (expires_at > issued_at),
    revoked_at timestamptz
);

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE download_grants, stored_files;
