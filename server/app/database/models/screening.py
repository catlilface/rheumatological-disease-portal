from sqlalchemy import (BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.database.base import Base
from app.database.models import enums



class ScreeningSession(Base):
    __tablename__ = 'screening_sessions'

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    session_token = Column(UUID(as_uuid=True), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    status = Column(enums.session_status, nullable=False, server_default=text("'in_progress'"))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ScreeningAnswer(Base):
    __tablename__ = 'screening_answers'
    __table_args__ = (
        UniqueConstraint('session_id', 'question_code'),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey('screening_sessions.id', ondelete='CASCADE'), nullable=False)
    question_code = Column(String(8), nullable=False)
    value = Column(JSONB(), nullable=False)
    weighted_score = Column(Integer(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class ScreeningResult(Base):
    __tablename__ = 'screening_results'

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    session_id = Column(UUID(as_uuid=True), ForeignKey('screening_sessions.id'), nullable=False, unique=True)
    block_scores = Column(JSONB(), nullable=False)
    total_score = Column(Integer(), nullable=False)
    red_flag_codes = Column(ARRAY(Text()), nullable=False, server_default=text("'{}'"))
    level = Column(enums.screening_level, nullable=False)
    weights_version = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
