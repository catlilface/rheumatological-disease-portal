"""MIS-23 access model refinements (2026-11-19): a generation (WSS
explanation request) records the subject it belongs to - "operationId/
jobs/WSS have owner_subject_id". result_projection.subject_id is left as
is: it mirrors Screening's own field, not an operation owner.
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE generations RENAME COLUMN subject_id TO owner_subject_id")


def downgrade() -> None:
    op.execute("ALTER TABLE generations RENAME COLUMN owner_subject_id TO subject_id")
