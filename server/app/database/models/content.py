from sqlalchemy import (BigInteger, Column, DateTime, ForeignKey, Index, Integer, Text, text)
from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base
from app.database.models import enums



class KnowledgeArticle(Base):
    __tablename__ = 'knowledge_articles'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    slug = Column(Text(), nullable=False, unique=True)
    disease_tag = Column(Text(), nullable=False)
    title = Column(Text(), nullable=False)
    body = Column(Text(), nullable=False)
    status = Column(enums.review_status, nullable=False, server_default=text("'draft'"))
    author_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    version = Column(Integer(), nullable=False, server_default=text('1'))
    published_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class AccessAudit(Base):
    __tablename__ = 'access_audit'

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(enums.audit_action, nullable=False)
    object_type = Column(Text(), nullable=False)
    object_id = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

Index('access_audit_patient_id_created_at_idx', AccessAudit.patient_id, AccessAudit.created_at)
