-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE report_jobs (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    operation_id uuid_v7 NOT NULL UNIQUE,
    owner_id uuid_v7 NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','ready','failed')),
    file_id uuid_v7,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status='ready') = (file_id IS NOT NULL))
);
CREATE TABLE report_snapshots (
    job_id uuid_v7 PRIMARY KEY REFERENCES report_jobs,
    result_id uuid_v7 NOT NULL,
    result_version bigint NOT NULL CHECK (result_version > 0),
    template_version text NOT NULL,
    locale text NOT NULL,
    key_id text NOT NULL, -- external key reference, never the encryption key
    encrypted_inputs bytea NOT NULL CHECK (octet_length(encrypted_inputs) > 0)
);
REVOKE UPDATE, DELETE ON report_snapshots FROM mis_reporting_app;

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE report_snapshots, report_jobs;
