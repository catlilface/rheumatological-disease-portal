DO $$ DECLARE subject uuid; BEGIN
    INSERT INTO principals(kind) VALUES ('guest') RETURNING id INTO subject;
    INSERT INTO access_audit(subject_id,resource_type,resource_id,action,allowed,reason_code)
        VALUES (subject,'report',uuidv7(),'read',false,'denied');
    DELETE FROM principals WHERE id=subject;
    IF NOT EXISTS (SELECT FROM access_audit WHERE subject_id=subject AND NOT allowed) THEN RAISE EXCEPTION 'lost audit'; END IF;
    BEGIN
        INSERT INTO principals(id,kind) VALUES (gen_random_uuid(),'guest');
        RAISE EXCEPTION 'accepted UUIDv4'; EXCEPTION WHEN check_violation THEN NULL;
    END;
END $$;
