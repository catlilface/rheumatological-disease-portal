"""MIS-23 access model refinements (2026-11-19): download grants separate
the file's owner (the patient) from the grant's recipient (e.g. a doctor),
track a grant version and the source that requested it, and rename
created_at to issued_at to match the TTL wording ("TTL 24 hours counted
from issuance"). Renewal creates a new grant row and revokes the old one -
an application-level rule, not a schema constraint.
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = (
    # Consistent naming with the rest of the MIS-23 refinement (IAM subject,
    # no FK, different database) - previously just "owner_id" here.
    """ALTER TABLE stored_files RENAME COLUMN owner_id TO owner_subject_id""",
    """ALTER TABLE download_grants RENAME COLUMN issued_to TO recipient_subject_id""",
    """ALTER TABLE download_grants RENAME COLUMN created_at TO issued_at""",
    # owner_subject_id: whose data this is (may differ from the recipient,
    # e.g. a doctor granted access to a patient's report).
    # version: this grant's revision in a renewal lineage (renewal = new row).
    # source_reference: what requested the grant, e.g. a Reporting job id;
    # no FK, different database.
    """ALTER TABLE download_grants
        ADD COLUMN owner_subject_id uuid,
        ADD COLUMN version integer NOT NULL DEFAULT 1,
        ADD COLUMN source_reference text""",
    """UPDATE download_grants SET owner_subject_id = recipient_subject_id WHERE owner_subject_id IS NULL""",
    """ALTER TABLE download_grants ALTER COLUMN owner_subject_id SET NOT NULL""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE download_grants DROP COLUMN owner_subject_id, DROP COLUMN version, "
        "DROP COLUMN source_reference",
    )
    op.execute("ALTER TABLE download_grants RENAME COLUMN issued_at TO created_at")
    op.execute("ALTER TABLE download_grants RENAME COLUMN recipient_subject_id TO issued_to")
    op.execute("ALTER TABLE stored_files RENAME COLUMN owner_subject_id TO owner_id")
