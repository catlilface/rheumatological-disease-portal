"""ORM mapping mirroring alembic/versions/0001_initial_schema.py and
0002_mis23_access_model.py exactly.

access_audit intentionally has no foreign keys to principals: a deleted
account's audit trail must survive the deletion (see service README).
"""

from rheuma_db import Base, register_inbox_model, register_outbox_model
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, ENUM, UUID

# Type is created and versioned by Alembic, not by metadata.create_all().
principal_kind = ENUM("guest", "employee", name="principal_kind", create_type=False)


class Principal(Base):
    __tablename__ = "principals"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'employee' AND email_hash IS NOT NULL) OR (kind = 'guest' AND email_hash IS NULL)",
            name="principal_kind_email_hash",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    kind = Column(principal_kind, nullable=False)
    email_hash = Column(BYTEA(), nullable=True, unique=True)
    password_hash = Column(Text(), nullable=True)
    display_name = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    principal_id = Column(UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False)
    session_token_hash = Column(BYTEA(), nullable=False, unique=True)
    issued_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    # MIS-23: refresh-token rotation and role-change/lockout invalidation.
    refresh_token_hash = Column(BYTEA(), nullable=True, unique=True)
    refresh_family_id = Column(UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()"))
    role_version = Column(Integer(), nullable=False, server_default=text("1"))
    locked_at = Column(DateTime(timezone=True), nullable=True)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("code IN ('patient', 'editor', 'admin')", name="roles_code_check"),
    )

    code = Column(Text(), primary_key=True, nullable=False)
    description = Column(Text(), nullable=False, server_default=text("''"))


class PrincipalRole(Base):
    """At most one active (non-revoked) role per principal - see the partial
    unique index in 0002_mis23_access_model; combining roles is forbidden."""

    __tablename__ = "principal_roles"
    __table_args__ = (PrimaryKeyConstraint("principal_id", "role_code"),)

    principal_id = Column(UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False)
    role_code = Column(Text(), ForeignKey("roles.code", ondelete="RESTRICT"), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (PrimaryKeyConstraint("role_code", "permission"),)

    role_code = Column(Text(), ForeignKey("roles.code", ondelete="CASCADE"), nullable=False)
    permission = Column(Text(), nullable=False)


class ResourceGrant(Base):
    __tablename__ = "resource_grants"
    __table_args__ = (
        UniqueConstraint("principal_id", "resource_type", "resource_id", "permission"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    principal_id = Column(UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(Text(), nullable=False)
    resource_id = Column(Text(), nullable=False)
    permission = Column(Text(), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class AccessAudit(Base):
    __tablename__ = "access_audit"

    id = Column(BigInteger(), primary_key=True, autoincrement=True, nullable=False)
    actor_principal_id = Column(UUID(as_uuid=True), nullable=False)
    subject_principal_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Text(), nullable=False)
    resource_type = Column(Text(), nullable=False)
    resource_id = Column(Text(), nullable=True)
    decision = Column(Text(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    # MIS-23: ties a decision to the session/operation it gated, and records why.
    session_id = Column(UUID(as_uuid=True), nullable=True)
    operation_id = Column(UUID(as_uuid=True), nullable=True)
    reason = Column(Text(), nullable=True)


Index("access_audit_subject_principal_id_created_at_idx", AccessAudit.subject_principal_id, AccessAudit.created_at)

OutboxEvent = register_outbox_model(Base)
InboxMessage = register_inbox_model(Base)
