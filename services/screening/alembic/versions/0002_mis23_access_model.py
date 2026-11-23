"""MIS-23 access model refinements (2026-11-19): rename owner_id to
owner_subject_id and require it even for guest sessions, and add a
configurable completion deadline (started_at + screeningCompletionTtlDays,
default 30 days) - a deadline to finish, not a result retention period.
"""

from alembic import op

revision = "0002_mis23_access_model"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = (
    # Every session - including guests - has a subject from IAM; it is no
    # longer optional. No FK: IAM owns that id in a different database.
    """ALTER TABLE screening_sessions RENAME COLUMN owner_id TO owner_subject_id""",
    """ALTER TABLE screening_sessions ALTER COLUMN owner_subject_id SET NOT NULL""",
    # Default mirrors started_at's own default; the admin-configurable TTL
    # itself (screeningCompletionTtlDays) lives in application config, not
    # in this column's default, which only applies at row-creation time.
    """ALTER TABLE screening_sessions
        ADD COLUMN completion_deadline_at timestamptz NOT NULL DEFAULT (now() + interval '30 days')""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE screening_sessions DROP COLUMN completion_deadline_at")
    op.execute("ALTER TABLE screening_sessions ALTER COLUMN owner_subject_id DROP NOT NULL")
    op.execute("ALTER TABLE screening_sessions RENAME COLUMN owner_subject_id TO owner_id")
