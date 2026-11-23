"""MIS-23 access model refinements (2026-11-19): single exclusive role per
principal (patient/editor/admin, no combining), refresh-token families and
role-version/lockout tracking on sessions, and audit extended with
session/operation/reason.
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = (
    # "editor" merges authoring and medical review; a principal holds at
    # most one of these three roles. Historical (revoked) rows are kept for
    # audit, so this is a partial index, not a plain UNIQUE(principal_id).
    """ALTER TABLE roles ADD CONSTRAINT roles_code_check
        CHECK (code IN ('patient', 'editor', 'admin'))""",
    """INSERT INTO roles (code, description) VALUES
        ('patient', 'Default role for registered and guest subjects'),
        ('editor', 'Authors and medically reviews content'),
        ('admin', 'Approves and publishes a specific content version')""",
    """CREATE UNIQUE INDEX principal_roles_one_active_idx
        ON principal_roles (principal_id) WHERE (revoked_at IS NULL)""",
    # Refresh-token rotation: all tokens descended from one login share a
    # family_id, so revoking the family revokes every rotated descendant.
    # role_version snapshots the principal's role assignment at issue time,
    # so a role change can invalidate sessions issued under the old role.
    """ALTER TABLE auth_sessions
        ADD COLUMN refresh_token_hash bytea UNIQUE,
        ADD COLUMN refresh_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
        ADD COLUMN role_version integer NOT NULL DEFAULT 1,
        ADD COLUMN locked_at timestamptz""",
    """ALTER TABLE access_audit
        ADD COLUMN session_id uuid,
        ADD COLUMN operation_id uuid,
        ADD COLUMN reason text""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE access_audit DROP COLUMN session_id, DROP COLUMN operation_id, DROP COLUMN reason")
    op.execute(
        "ALTER TABLE auth_sessions DROP COLUMN refresh_token_hash, DROP COLUMN refresh_family_id, "
        "DROP COLUMN role_version, DROP COLUMN locked_at",
    )
    op.execute("DROP INDEX principal_roles_one_active_idx")
    op.execute("DELETE FROM roles WHERE code IN ('patient', 'editor', 'admin')")
    op.execute("ALTER TABLE roles DROP CONSTRAINT roles_code_check")
