"""MIS-23 access model refinements (2026-11-19): materials track who
approved them and which version was approved, separately from who merely
reviewed a given version (material_versions.reviewer_id). Editing the text
always means a new, unapproved version (enforced by the application, not
by this migration).
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = (
    # approved_by is an IAM admin subject id; no FK, different database.
    # approved_version points at the material's own version row, so it can
    # be FK'd within this database (set only after that version exists).
    """ALTER TABLE materials
        ADD COLUMN approved_by uuid,
        ADD COLUMN approved_version bigint""",
    """ALTER TABLE materials
        ADD CONSTRAINT materials_approved_version_fkey
        FOREIGN KEY (id, approved_version) REFERENCES material_versions (material_id, version)""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE materials DROP CONSTRAINT materials_approved_version_fkey")
    op.execute("ALTER TABLE materials DROP COLUMN approved_by, DROP COLUMN approved_version")
