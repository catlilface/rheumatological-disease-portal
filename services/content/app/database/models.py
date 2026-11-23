"""ORM mapping mirroring alembic/versions/0001_initial_schema.py and
0002_mis23_access_model.py exactly.

material_versions has no DB-level trigger enforcing "at most one published
version" directly on the ORM side either - that invariant is the partial
unique index created in the migration (see README), not expressible as a
plain SQLAlchemy UniqueConstraint.
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID

# Types are created and versioned by Alembic, not by metadata.create_all().
material_kind = ENUM("article", "doctor_route", name="material_kind", create_type=False)
review_status = ENUM("draft", "under_review", "approved", "published", name="review_status", create_type=False)


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "approved_version"], ["material_versions.material_id", "material_versions.version"],
        ),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    kind = Column(material_kind, nullable=False)
    slug = Column(Text(), nullable=False, unique=True)
    disease_tag = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    # MIS-23: who approved this material and which version - distinct from
    # material_versions.reviewer_id, which only tracks who reviewed a version.
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_version = Column(BigInteger(), nullable=True)


class MaterialVersion(Base):
    __tablename__ = "material_versions"
    __table_args__ = (
        UniqueConstraint("material_id", "version"),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    material_id = Column(BigInteger(), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    version = Column(BigInteger(), nullable=False)
    title = Column(Text(), nullable=False)
    summary = Column(Text(), nullable=True)
    body_markdown = Column(Text(), nullable=False)
    status = Column(review_status, nullable=False, server_default=text("'draft'"))
    author_id = Column(UUID(as_uuid=True), nullable=True)
    reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class MaterialSource(Base):
    __tablename__ = "material_sources"

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    material_version_id = Column(
        BigInteger(), ForeignKey("material_versions.id", ondelete="CASCADE"), nullable=False,
    )
    title = Column(Text(), nullable=False)
    url = Column(Text(), nullable=False)


OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
