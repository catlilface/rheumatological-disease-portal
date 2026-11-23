"""ORM mapping mirroring alembic/versions/0001_initial_schema.py and
0002_mis23_access_model.py exactly.

File *content* lives in SeaweedFS, not here - this database only stores
metadata and access grants (see service README).
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    object_key = Column(Text(), nullable=False, unique=True)
    owner_subject_id = Column(UUID(as_uuid=True), nullable=False)
    source_service = Column(Text(), nullable=False)
    source_reference = Column(Text(), nullable=True)
    size_bytes = Column(BigInteger(), nullable=False)
    checksum_sha256 = Column(BYTEA(), nullable=False)
    content_type = Column(Text(), nullable=False, server_default=text("'application/pdf'"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DownloadGrant(Base):
    __tablename__ = "download_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    stored_file_id = Column(UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="CASCADE"), nullable=False)
    # MIS-23: the file's owner (patient) vs. this grant's recipient (e.g. a
    # doctor) - these can differ. Neither has a FK: IAM owns that id.
    owner_subject_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_subject_id = Column(UUID(as_uuid=True), nullable=False)
    token_hash = Column(BYTEA(), nullable=False, unique=True)
    # This grant's revision in a renewal lineage; renewal = new row + revoke old.
    version = Column(Integer(), nullable=False, server_default=text("1"))
    # What requested the grant, e.g. a Reporting job id; no FK, different database.
    source_reference = Column(Text(), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
