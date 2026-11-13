from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, SmallInteger, String, Text, text)
from sqlalchemy.dialects.postgresql import BYTEA, UUID

from app.database.base import Base
from app.database.models import enums



class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    email_hash = Column(BYTEA(), nullable=False, unique=True)
    password_hash = Column(Text(), nullable=False)
    role = Column(enums.user_role, nullable=False, server_default=text("'patient'"))
    consent_version = Column(Text(), nullable=False)
    consent_accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class PatientProfile(Base):
    __tablename__ = 'patient_profiles'
    __table_args__ = (
        CheckConstraint('year_of_birth BETWEEN 1920 AND 2025', name='year_of_birth'),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    year_of_birth = Column(SmallInteger(), nullable=True)
    sex = Column(enums.sex, nullable=True)
    diagnosis_code = Column(String(8), nullable=True)
    diagnosis_confirmed_by_doctor = Column(Boolean(), nullable=False, server_default=text('false'))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
