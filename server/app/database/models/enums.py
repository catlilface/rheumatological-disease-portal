from sqlalchemy.dialects.postgresql import ENUM


# Types are created and versioned by Alembic, not by metadata.create_all().
user_role = ENUM('patient', 'admin', 'medical_reviewer', name='user_role', create_type=False)
sex = ENUM('male', 'female', 'undisclosed', name='sex', create_type=False)
session_status = ENUM('in_progress', 'completed', 'abandoned', name='session_status', create_type=False)
screening_level = ENUM('low', 'medium', 'high', 'red_flag', name='screening_level', create_type=False)
intake_status = ENUM('taken', 'skipped', 'delayed', name='intake_status', create_type=False)
data_source = ENUM('patient', 'doctor', name='data_source', create_type=False)
review_status = ENUM('draft', 'under_review', 'approved', 'published', name='review_status', create_type=False)
reminder_type = ENUM('medication', 'visit', 'lab', name='reminder_type', create_type=False)
audit_action = ENUM('read', 'create', 'update', 'delete', 'export', name='audit_action', create_type=False)
