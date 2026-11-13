from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Numeric, SmallInteger, Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID

from app.database.base import Base
from app.database.models import enums



class SymptomEntry(Base):
    __tablename__ = 'symptom_entries'
    __table_args__ = (
        CheckConstraint('pain_vas BETWEEN 0 AND 10', name='pain_vas'),
        CheckConstraint('morning_stiffness_min BETWEEN 0 AND 1440', name='morning_stiffness_min'),
        CheckConstraint('swollen_joints_selfreport >= 0', name='swollen_joints_selfreport'),
        CheckConstraint('painful_joints_selfreport >= 0', name='painful_joints_selfreport'),
        CheckConstraint('fatigue_vas BETWEEN 0 AND 10', name='fatigue_vas'),
        UniqueConstraint('user_id', 'entry_date'),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    entry_date = Column(Date(), nullable=False)
    pain_vas = Column(SmallInteger(), nullable=True)
    morning_stiffness_min = Column(SmallInteger(), nullable=True)
    swollen_joints_selfreport = Column(SmallInteger(), nullable=True)
    painful_joints_selfreport = Column(SmallInteger(), nullable=True)
    fatigue_vas = Column(SmallInteger(), nullable=True)
    flares = Column(Boolean(), nullable=False, server_default=text('false'))
    notes_enc = Column(BYTEA(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Medication(Base):
    __tablename__ = 'medications'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text(), nullable=False)
    dose = Column(Text(), nullable=True)
    schedule = Column(JSONB(), nullable=False)
    start_date = Column(Date(), nullable=True)
    end_date = Column(Date(), nullable=True)
    is_active = Column(Boolean(), nullable=False, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class MedicationIntakeLog(Base):
    __tablename__ = 'medication_intake_log'
    __table_args__ = (
        UniqueConstraint('medication_id', 'scheduled_date'),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    medication_id = Column(BigInteger(), ForeignKey('medications.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    scheduled_date = Column(Date(), nullable=False)
    taken_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(enums.intake_status, nullable=False)
    reason_skipped = Column(Text(), nullable=True)


class LabResult(Base):
    __tablename__ = 'lab_results'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    test_code = Column(Text(), nullable=False)
    value = Column(Numeric(), nullable=False)
    unit = Column(Text(), nullable=True)
    lab_date = Column(Date(), nullable=False)
    reference_range = Column(JSONB(), nullable=True)
    entered_by = Column(enums.data_source, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Visit(Base):
    __tablename__ = 'visits'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    visit_date = Column(Date(), nullable=False)
    doctor_specialty = Column(Text(), nullable=True)
    notes_enc = Column(BYTEA(), nullable=True)
    next_visit_date = Column(Date(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = Column(enums.reminder_type, nullable=False)
    related_id = Column(BigInteger(), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text(), nullable=False, server_default=text("'pending'"))


class ReportExport(Base):
    __tablename__ = 'report_exports'

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text('gen_random_uuid()'))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    period_start = Column(Date(), nullable=False)
    period_end = Column(Date(), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    file_ref = Column(Text(), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    downloaded_at = Column(DateTime(timezone=True), nullable=True)

Index('symptom_entries_user_id_entry_date_idx', SymptomEntry.user_id, SymptomEntry.entry_date.desc())

Index('medication_intake_log_user_id_scheduled_date_idx', MedicationIntakeLog.user_id, MedicationIntakeLog.scheduled_date)

Index('lab_results_user_id_lab_date_idx', LabResult.user_id, LabResult.lab_date)
