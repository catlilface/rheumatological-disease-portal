"""Initial schema from Supplement 1, section 2."""

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Frozen SQL snapshot: never import mutable application metadata in this revision.
STATEMENTS = (
    """CREATE TYPE user_role        AS ENUM ('patient','admin','medical_reviewer')""",
    """CREATE TYPE sex              AS ENUM ('male','female','undisclosed')""",
    """CREATE TYPE session_status   AS ENUM ('in_progress','completed','abandoned')""",
    """CREATE TYPE screening_level  AS ENUM ('low','medium','high','red_flag')""",
    """CREATE TYPE intake_status    AS ENUM ('taken','skipped','delayed')""",
    """CREATE TYPE data_source      AS ENUM ('patient','doctor')""",
    """CREATE TYPE review_status    AS ENUM ('draft','under_review','approved','published')""",
    """CREATE TYPE reminder_type    AS ENUM ('medication','visit','lab')""",
    """CREATE TYPE audit_action     AS ENUM ('read','create','update','delete','export')""",
    """CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_hash        bytea UNIQUE NOT NULL,
    password_hash     text    NOT NULL,
    role              user_role NOT NULL DEFAULT 'patient',
    consent_version   text    NOT NULL,
    consent_accepted_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE patient_profiles (
    user_id                     uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    year_of_birth               smallint CHECK (year_of_birth BETWEEN 1920 AND 2025),
    sex                         sex,
    diagnosis_code              varchar(8),
    diagnosis_confirmed_by_doctor boolean NOT NULL DEFAULT false,
    updated_at                  timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE screening_sessions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_token uuid UNIQUE NOT NULL,
    user_id       uuid REFERENCES users(id),
    status        session_status NOT NULL DEFAULT 'in_progress',
    started_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
)""",
    """CREATE TABLE screening_answers (
    id            bigserial PRIMARY KEY,
    session_id    uuid NOT NULL REFERENCES screening_sessions(id) ON DELETE CASCADE,
    question_code varchar(8) NOT NULL,
    value         jsonb NOT NULL,
    weighted_score integer NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, question_code)
)""",
    """CREATE TABLE screening_results (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid UNIQUE NOT NULL REFERENCES screening_sessions(id),
    block_scores    jsonb NOT NULL,
    total_score     integer NOT NULL,
    red_flag_codes  text[] NOT NULL DEFAULT '{}',
    level           screening_level NOT NULL,
    weights_version varchar(16) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE symptom_entries (
    id                         bigserial PRIMARY KEY,
    user_id                    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date                 date NOT NULL,
    pain_vas                   smallint CHECK (pain_vas BETWEEN 0 AND 10),
    morning_stiffness_min      smallint CHECK (morning_stiffness_min BETWEEN 0 AND 1440),
    swollen_joints_selfreport  smallint CHECK (swollen_joints_selfreport >= 0),
    painful_joints_selfreport  smallint CHECK (painful_joints_selfreport >= 0),
    fatigue_vas                smallint CHECK (fatigue_vas BETWEEN 0 AND 10),
    flares                     boolean NOT NULL DEFAULT false,
    notes_enc                  bytea,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, entry_date)
)""",
    """CREATE TABLE medications (
    id         bigserial PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    dose       text,
    schedule   jsonb NOT NULL,
    start_date date,
    end_date   date,
    is_active  boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE medication_intake_log (
    id             bigserial PRIMARY KEY,
    medication_id  bigint NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    user_id        uuid   NOT NULL REFERENCES users(id),
    scheduled_date date   NOT NULL,
    taken_at       timestamptz,
    status         intake_status NOT NULL,
    reason_skipped text,
    UNIQUE (medication_id, scheduled_date)
)""",
    """CREATE TABLE lab_results (
    id              bigserial PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_code       text NOT NULL,
    value           numeric NOT NULL,
    unit            text,
    lab_date        date NOT NULL,
    reference_range jsonb,
    entered_by      data_source NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE visits (
    id              bigserial PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    visit_date      date NOT NULL,
    doctor_specialty text,
    notes_enc       bytea,
    next_visit_date date,
    created_at      timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE reminders (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         reminder_type NOT NULL,
    related_id   bigint,
    scheduled_at timestamptz NOT NULL,
    sent_at      timestamptz,
    status       text NOT NULL DEFAULT 'pending'
)""",
    """CREATE TABLE report_exports (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start  date NOT NULL,
    period_end    date NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now(),
    file_ref      text,
    expires_at    timestamptz NOT NULL,
    downloaded_at timestamptz
)""",
    """CREATE TABLE knowledge_articles (
    id           bigserial PRIMARY KEY,
    slug         text UNIQUE NOT NULL,
    disease_tag  text NOT NULL,
    title        text NOT NULL,
    body         text NOT NULL,
    status       review_status NOT NULL DEFAULT 'draft',
    author_id    uuid REFERENCES users(id),
    reviewer_id  uuid REFERENCES users(id),
    version      integer NOT NULL DEFAULT 1,
    published_at timestamptz,
    updated_at   timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE access_audit (
    id             bigserial PRIMARY KEY,
    actor_user_id  uuid REFERENCES users(id),
    patient_id     uuid NOT NULL,
    action         audit_action NOT NULL,
    object_type    text NOT NULL,
    object_id      text,
    created_at     timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE INDEX symptom_entries_user_id_entry_date_idx ON symptom_entries (user_id, entry_date DESC)""",
    """CREATE INDEX medication_intake_log_user_id_scheduled_date_idx ON medication_intake_log (user_id, scheduled_date)""",
    """CREATE INDEX lab_results_user_id_lab_date_idx ON lab_results (user_id, lab_date)""",
    """CREATE INDEX access_audit_patient_id_created_at_idx ON access_audit (patient_id, created_at)""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name in ('access_audit', 'knowledge_articles', 'report_exports', 'reminders', 'visits', 'lab_results', 'medication_intake_log', 'medications', 'symptom_entries', 'screening_results', 'screening_answers', 'screening_sessions', 'patient_profiles', 'users'):
        op.drop_table(table_name)
    for type_name in ('audit_action', 'reminder_type', 'review_status', 'data_source', 'intake_status', 'screening_level', 'session_status', 'sex', 'user_role'):
        op.execute("DROP TYPE " + type_name)
