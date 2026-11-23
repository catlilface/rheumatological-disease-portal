"""ORM mapping mirroring alembic/versions/0001_initial_schema.py and
0002_mis23_access_model.py exactly.

result_id/file_id/owner_subject_id have no foreign keys: Screening, Files,
and IAM own those rows in different databases (see service README).
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import BYTEA, ENUM, UUID

# Type is created and versioned by Alembic, not by metadata.create_all().
report_status = ENUM("pending", "generating", "ready", "failed", name="report_status", create_type=False)


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    operation_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    # MIS-23: fileId/operationId are not themselves an authorization; the
    # owning subject is tracked explicitly.
    owner_subject_id = Column(UUID(as_uuid=True), nullable=False)
    result_id = Column(UUID(as_uuid=True), nullable=False)
    result_version = Column(BigInteger(), nullable=False)
    template_version = Column(Text(), nullable=False)
    locale = Column(Text(), nullable=False)
    status = Column(report_status, nullable=False, server_default=text("'pending'"))
    file_id = Column(UUID(as_uuid=True), nullable=True)
    failure_code = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    generated_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(BigInteger(), nullable=False, server_default=text("1"))


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    report_job_id = Column(UUID(as_uuid=True), ForeignKey("report_jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    template_version = Column(Text(), nullable=False)
    encrypted_input = Column(BYTEA(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
