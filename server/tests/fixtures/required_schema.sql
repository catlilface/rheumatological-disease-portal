-- Reference DDL copied from Supplement 1, section 2.
-- The four non-unique indexes below express its mandatory index list.
-- screening_sessions(session_token) is already indexed by UNIQUE.

CREATE TYPE user_role        AS ENUM ('patient','admin','medical_reviewer');

CREATE TYPE sex              AS ENUM ('male','female','undisclosed');

CREATE TYPE session_status   AS ENUM ('in_progress','completed','abandoned');

CREATE TYPE screening_level  AS ENUM ('low','medium','high','red_flag');

CREATE TYPE intake_status    AS ENUM ('taken','skipped','delayed');

CREATE TYPE data_source      AS ENUM ('patient','doctor');

CREATE TYPE review_status    AS ENUM ('draft','under_review','approved','published');

CREATE TYPE reminder_type    AS ENUM ('medication','visit','lab');

CREATE TYPE audit_action     AS ENUM ('read','create','update','delete','export');

CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_hash        bytea UNIQUE NOT NULL,          -- HMAC-SHA256(email, ключ из ENV)
    password_hash     text    NOT NULL,               -- argon2/bcrypt
    role              user_role NOT NULL DEFAULT 'patient',
    consent_version   text    NOT NULL,               -- идентификатор версии согласия
    consent_accepted_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patient_profiles (
    user_id                     uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    year_of_birth               smallint CHECK (year_of_birth BETWEEN 1920 AND 2025), -- только год, дата запрещена
    sex                         sex,
    diagnosis_code              varchar(8),          -- код МКБ-10, опционально
    diagnosis_confirmed_by_doctor boolean NOT NULL DEFAULT false,
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE screening_sessions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_token uuid UNIQUE NOT NULL,               -- идентификатор для гостя (без регистрации)
    user_id       uuid REFERENCES users(id),          -- NULL до «мягкой регистрации»
    status        session_status NOT NULL DEFAULT 'in_progress',
    started_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
);

CREATE TABLE screening_answers (
    id            bigserial PRIMARY KEY,
    session_id    uuid NOT NULL REFERENCES screening_sessions(id) ON DELETE CASCADE,
    question_code varchar(8) NOT NULL,               -- 'A1'..'A8','Б1'..'Б7','В1'..'В4','Г1'..'Г3'
    value         jsonb NOT NULL,                    -- значение ответа в формате из JSON-контракта
    weighted_score integer NOT NULL,                 -- вес, посчитанный движком
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, question_code)
);

CREATE TABLE screening_results (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid UNIQUE NOT NULL REFERENCES screening_sessions(id),
    block_scores    jsonb NOT NULL,                  -- {"A": 7, "Б": 4, "Г": 2}
    total_score     integer NOT NULL,
    red_flag_codes  text[] NOT NULL DEFAULT '{}',    -- сработавшие В-вопросы: ARRAY['В2']
    level           screening_level NOT NULL,
    weights_version varchar(16) NOT NULL,            -- версия весов/порогов ('draft-v1' до подтверждения куратором)
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE symptom_entries (
    id                         bigserial PRIMARY KEY,
    user_id                    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date                 date NOT NULL,
    pain_vas                   smallint CHECK (pain_vas BETWEEN 0 AND 10),
    morning_stiffness_min      smallint CHECK (morning_stiffness_min BETWEEN 0 AND 1440),
    swollen_joints_selfreport  smallint CHECK (swollen_joints_selfreport >= 0),
    painful_joints_selfreport  smallint CHECK (painful_joints_selfreport >= 0),
    fatigue_vas                smallint CHECK (fatigue_vas BETWEEN 0 AND 10),
    flares                     boolean NOT NULL DEFAULT false,
    notes_enc                  bytea,                -- зашифровано на уровне приложения
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, entry_date)                    -- не более одной записи в день (правило B4)
);

CREATE TABLE medications (
    id         bigserial PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    dose       text,
    schedule   jsonb NOT NULL,                       -- {"days":[1,3,5],"times":["08:00","20:00"]}
    start_date date,
    end_date   date,
    is_active  boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE medication_intake_log (
    id             bigserial PRIMARY KEY,
    medication_id  bigint NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    user_id        uuid   NOT NULL REFERENCES users(id),   -- денормализовано для аудита
    scheduled_date date   NOT NULL,
    taken_at       timestamptz,
    status         intake_status NOT NULL,
    reason_skipped text,                             -- 'forgot' / 'side_effect' / другое
    UNIQUE (medication_id, scheduled_date)
);

CREATE TABLE lab_results (
    id              bigserial PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_code       text NOT NULL,                   -- 'CRP','ESR','ACPA','RF','ANA'
    value           numeric NOT NULL,
    unit            text,
    lab_date        date NOT NULL,
    reference_range jsonb,
    entered_by      data_source NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE visits (
    id              bigserial PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    visit_date      date NOT NULL,
    doctor_specialty text,
    notes_enc       bytea,
    next_visit_date date,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reminders (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         reminder_type NOT NULL,
    related_id   bigint,                             -- id препарата/визита/анализа
    scheduled_at timestamptz NOT NULL,
    sent_at      timestamptz,
    status       text NOT NULL DEFAULT 'pending'
);

CREATE TABLE report_exports (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start  date NOT NULL,
    period_end    date NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now(),
    file_ref      text,                              -- ссылка на зашифрованный файл
    expires_at    timestamptz NOT NULL,              -- generated_at + 24 ч
    downloaded_at timestamptz
);

CREATE TABLE knowledge_articles (
    id           bigserial PRIMARY KEY,
    slug         text UNIQUE NOT NULL,
    disease_tag  text NOT NULL,                      -- 'RA','GOUT','SLE','SPA'
    title        text NOT NULL,
    body         text NOT NULL,                      -- markdown по шаблону ТЗ
    status       review_status NOT NULL DEFAULT 'draft',
    author_id    uuid REFERENCES users(id),
    reviewer_id  uuid REFERENCES users(id),          -- куратор-врач / medical_reviewer
    version      integer NOT NULL DEFAULT 1,
    published_at timestamptz,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE access_audit (
    id             bigserial PRIMARY KEY,
    actor_user_id  uuid REFERENCES users(id),        -- кто
    patient_id     uuid NOT NULL,                    -- чьи данные (не FK: лог живёт дольше пользователя)
    action         audit_action NOT NULL,
    object_type    text NOT NULL,                    -- 'symptom_entries','report_exports',...
    object_id      text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX symptom_entries_user_id_entry_date_idx ON symptom_entries (user_id, entry_date DESC);

CREATE INDEX medication_intake_log_user_id_scheduled_date_idx ON medication_intake_log (user_id, scheduled_date);

CREATE INDEX lab_results_user_id_lab_date_idx ON lab_results (user_id, lab_date);

CREATE INDEX access_audit_patient_id_created_at_idx ON access_audit (patient_id, created_at);
