"""ORM mapping mirroring alembic/versions/0001_initial_schema.py exactly.

result_projection/article_projection are local, possibly-lagging copies of
Screening/Content data (events update them) - not the source of truth, and
not foreign-keyed to anything outside this database (see service README).
Embeddings use a plain float array rather than the `vector` type/pgvector
extension, to avoid an extra Postgres extension dependency nobody asked for
yet; swapping to pgvector is a documented future optimization.
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


class ResultProjection(Base):
    __tablename__ = "result_projection"
    __table_args__ = (PrimaryKeyConstraint("result_id", "version"),)

    result_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(BigInteger(), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    block_scores = Column(JSONB(), nullable=False)
    total_score = Column(Integer(), nullable=True)
    level = Column(Text(), nullable=False)
    red_flag_codes = Column(ARRAY(Text()), nullable=False, server_default=text("'{}'"))
    recommendations = Column(JSONB(), nullable=False, server_default=text("'[]'"))
    disclaimer = Column(Text(), nullable=False)
    projected_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ArticleProjection(Base):
    __tablename__ = "article_projection"
    __table_args__ = (PrimaryKeyConstraint("article_id", "version"),)

    article_id = Column(BigInteger(), nullable=False)
    version = Column(BigInteger(), nullable=False)
    slug = Column(Text(), nullable=False)
    disease_tag = Column(Text(), nullable=True)
    title = Column(Text(), nullable=False)
    summary = Column(Text(), nullable=True)
    status = Column(Text(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    projected_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ArticleChunk(Base):
    __tablename__ = "article_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["article_id", "version"],
            ["article_projection.article_id", "article_projection.version"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("article_id", "version", "chunk_index"),
    )

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    article_id = Column(BigInteger(), nullable=False)
    version = Column(BigInteger(), nullable=False)
    chunk_index = Column(Integer(), nullable=False)
    content = Column(Text(), nullable=False)


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    chunk_id = Column(BigInteger(), ForeignKey("article_chunks.id", ondelete="CASCADE"), primary_key=True)
    model = Column(Text(), nullable=False)
    embedding = Column(ARRAY(Float()), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_id", "result_version"],
            ["result_projection.result_id", "result_projection.version"],
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    result_id = Column(UUID(as_uuid=True), nullable=False)
    result_version = Column(BigInteger(), nullable=False)
    # MIS-23: "operationId/jobs/WSS have owner_subject_id" - renamed from subject_id.
    owner_subject_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text(), nullable=False, server_default=text("'pending'"))
    answer = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class GenerationSource(Base):
    __tablename__ = "generation_sources"
    __table_args__ = (PrimaryKeyConstraint("generation_id", "chunk_id"),)

    generation_id = Column(UUID(as_uuid=True), ForeignKey("generations.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(BigInteger(), ForeignKey("article_chunks.id"), nullable=False)


OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
