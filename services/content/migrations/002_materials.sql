-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE materials (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    kind text NOT NULL CHECK (kind IN ('article','doctor_route')),
    slug text NOT NULL UNIQUE
);
CREATE TABLE material_versions (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    material_id uuid_v7 NOT NULL REFERENCES materials,
    version bigint NOT NULL CHECK (version > 0),
    title text NOT NULL,
    summary text NOT NULL,
    body_markdown text NOT NULL,
    disease_tag text,
    author_id uuid_v7 NOT NULL,
    reviewer_id uuid_v7,
    reviewed_at timestamptz,
    status text NOT NULL CHECK (status IN ('draft','under_review','approved','published','archived')),
    CHECK (status NOT IN ('approved','published') OR (reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)),
    UNIQUE (material_id, version)
);
CREATE UNIQUE INDEX one_public_version ON material_versions(material_id) WHERE status='published';
CREATE TABLE material_sources (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    version_id uuid_v7 NOT NULL REFERENCES material_versions ON DELETE CASCADE,
    title text NOT NULL,
    url text NOT NULL
);

-- migrate:down
SET LOCAL search_path = public;
DROP TABLE material_sources, material_versions, materials;
