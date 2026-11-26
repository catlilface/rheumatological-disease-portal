-- migrate:up
SET LOCAL search_path = public;
-- Keep the revocation even if the operator later clears blocked_at.
CREATE FUNCTION revoke_blocked_sessions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE public.auth_sessions SET revoked_at = NEW.blocked_at
        WHERE principal_id = NEW.id AND revoked_at IS NULL;
    RETURN NEW;
END $$;
CREATE TRIGGER block_sessions AFTER UPDATE OF blocked_at ON principals
    FOR EACH ROW WHEN (NEW.blocked_at IS NOT NULL AND OLD.blocked_at IS NULL)
    EXECUTE FUNCTION revoke_blocked_sessions();

-- migrate:down
SET LOCAL search_path = public;
DROP TRIGGER block_sessions ON principals;
DROP FUNCTION revoke_blocked_sessions();
