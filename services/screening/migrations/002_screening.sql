-- migrate:up
SET LOCAL search_path = public;
CREATE TABLE questionnaire_versions (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    survey_code text NOT NULL,
    weights_version text NOT NULL,
    disclaimer_version text NOT NULL,
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition)='object'),
    UNIQUE (survey_code, weights_version, disclaimer_version)
);
REVOKE UPDATE, DELETE ON questionnaire_versions FROM mis_screening_app;
CREATE TABLE screening_sessions (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    owner_id uuid_v7 NOT NULL, -- IAM subject (including a guest), never a remote FK
    questionnaire_version_id uuid_v7 NOT NULL REFERENCES questionnaire_versions,
    disclaimer_accepted_at timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    status text NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','abandoned')),
    final_result_id uuid_v7,
    CHECK ((status='completed') = (final_result_id IS NOT NULL))
);
CREATE TABLE screening_answers (
    session_id uuid_v7 REFERENCES screening_sessions,
    question_code text NOT NULL,
    value jsonb NOT NULL CHECK (jsonb_typeof(value) IN ('boolean','string')),
    weighted_score integer NOT NULL,
    PRIMARY KEY (session_id, question_code)
);
CREATE TABLE screening_results (
    id uuid_v7 PRIMARY KEY DEFAULT uuidv7(),
    session_id uuid_v7 NOT NULL UNIQUE REFERENCES screening_sessions,
    -- Exact MIS-22 revision n is revisions -> (n-1). Each element is a full snapshot.
    revisions jsonb NOT NULL CHECK (jsonb_typeof(revisions)='array'),
    version integer GENERATED ALWAYS AS (jsonb_array_length(revisions)) STORED,
    UNIQUE (session_id, id)
);
-- Both existence and ownership of the final result are checked at COMMIT, so a
-- service can write both sides (and the outbox) in one local transaction.
ALTER TABLE screening_sessions ADD CONSTRAINT final_result_of_this_session
    FOREIGN KEY (id, final_result_id) REFERENCES screening_results(session_id, id) DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION guard_result_revision() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE session_status text; level text := NEW.revisions -> -1 ->> 'level';
BEGIN
    IF level IS NULL OR level NOT IN ('LOW','MEDIUM','HIGH','RED_FLAG') THEN
        RAISE EXCEPTION 'Invalid result level' USING ERRCODE='23514';
    END IF;
    IF TG_OP='INSERT' THEN
        IF jsonb_array_length(NEW.revisions) <> 1 THEN
            RAISE EXCEPTION 'First result must have one revision' USING ERRCODE='23514';
        END IF;
    ELSE
        -- Serialize with completion of the same session; the final row cannot be revised.
        SELECT status INTO STRICT session_status FROM screening_sessions WHERE id=OLD.session_id FOR UPDATE;
        IF session_status='completed' OR NEW.session_id<>OLD.session_id OR NEW.id<>OLD.id
           OR jsonb_array_length(NEW.revisions) <> OLD.version+1
           OR (NEW.revisions - -1) IS DISTINCT FROM OLD.revisions
           OR (OLD.revisions -> -1 ->> 'level' = 'RED_FLAG' AND level <> 'RED_FLAG') THEN
            RAISE EXCEPTION 'Cannot replace result history or revise a final result' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_revision BEFORE INSERT OR UPDATE ON screening_results FOR EACH ROW EXECUTE FUNCTION guard_result_revision();
REVOKE DELETE ON screening_results FROM mis_screening_app;

-- Only mutable session columns are granted. This pins the subject, questionnaire,
-- scoring rules and accepted disclaimer at creation, without duplicating them.
REVOKE UPDATE ON screening_sessions FROM mis_screening_app;
GRANT UPDATE (version, status, final_result_id) ON screening_sessions TO mis_screening_app;
CREATE FUNCTION guard_completed_session() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status='completed' THEN RAISE EXCEPTION 'Session is final' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_completed BEFORE UPDATE ON screening_sessions FOR EACH ROW EXECUTE FUNCTION guard_completed_session();

-- migrate:down
SET LOCAL search_path = public;
ALTER TABLE screening_sessions DROP CONSTRAINT final_result_of_this_session;
DROP TABLE screening_results, screening_answers, screening_sessions, questionnaire_versions;
DROP FUNCTION guard_result_revision(), guard_completed_session();
