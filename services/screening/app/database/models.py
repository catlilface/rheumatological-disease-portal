"""ORM mapping mirroring alembic/versions/0001_initial_schema.py and
0002_mis23_access_model.py exactly.

screening_sessions.owner_subject_id has no foreign key: it is an IAM
subject id, a different service's database (see service README).
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

# Types are created and versioned by Alembic, not by metadata.create_all().
session_status = ENUM("in_progress", "completed", "abandoned", name="session_status", create_type=False)
screening_level = ENUM("low", "medium", "high", "red_flag", name="screening_level", create_type=False)


class QuestionnaireVersion(Base):
    __tablename__ = "questionnaire_versions"

    survey_id = Column(Text(), primary_key=True, nullable=False)
    weights_version = Column(Text(), primary_key=True, nullable=False)
    definition = Column(JSONB(), nullable=False)
    disclaimer = Column(Text(), nullable=False)
    disclaimer_version = Column(Text(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ScreeningSession(Base):
    __tablename__ = "screening_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["survey_id", "weights_version"],
            ["questionnaire_versions.survey_id", "questionnaire_versions.weights_version"],
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    session_token = Column(UUID(as_uuid=True), nullable=False, unique=True)
    # Required even for guests (MIS-23): every session has an IAM subject.
    owner_subject_id = Column(UUID(as_uuid=True), nullable=False)
    survey_id = Column(Text(), nullable=False)
    weights_version = Column(Text(), nullable=False)
    status = Column(session_status, nullable=False, server_default=text("'in_progress'"))
    interrupted_by_red_flag = Column(Boolean(), nullable=False, server_default=text("false"))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Deadline to finish the questionnaire (started_at + admin-configurable
    # TTL, default 30 days) - not a result retention period.
    completion_deadline_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now() + interval '30 days'"),
    )
    version = Column(BigInteger(), nullable=False, server_default=text("1"))


class ScreeningAnswer(Base):
    __tablename__ = "screening_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_code"),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), nullable=False)
    question_code = Column(String(8), nullable=False)
    value = Column(JSONB(), nullable=False)
    weighted_score = Column(Integer(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    session_id = Column(UUID(as_uuid=True), ForeignKey("screening_sessions.id"), nullable=False, unique=True)
    version = Column(BigInteger(), nullable=False, server_default=text("1"))
    block_scores = Column(JSONB(), nullable=False)
    total_score = Column(Integer(), nullable=True)
    scoring_complete = Column(Boolean(), nullable=False, server_default=text("false"))
    red_flag_codes = Column(ARRAY(Text()), nullable=False, server_default=text("'{}'"))
    level = Column(screening_level, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
