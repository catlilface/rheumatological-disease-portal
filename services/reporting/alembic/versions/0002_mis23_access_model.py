"""MIS-23 access model refinements (2026-11-19): a report job records the
subject it belongs to - "operationId/jobs/WSS have owner_subject_id;
fileId and operationId are not themselves an authorization".
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = (
    # owner_subject_id is an IAM subject id; no FK, different database.
    # Backfilled from result_id as a placeholder for pre-existing rows -
    # this dev stand has none yet, but a real deployment would need a
    # real backfill instead of borrowing an unrelated column.
    """ALTER TABLE report_jobs ADD COLUMN owner_subject_id uuid""",
    """UPDATE report_jobs SET owner_subject_id = result_id WHERE owner_subject_id IS NULL""",
    """ALTER TABLE report_jobs ALTER COLUMN owner_subject_id SET NOT NULL""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE report_jobs DROP COLUMN owner_subject_id")
