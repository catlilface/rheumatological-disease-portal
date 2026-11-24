DO $$ DECLARE op uuid := uuidv7(); job uuid; BEGIN
    INSERT INTO report_jobs(operation_id,owner_id) VALUES (op,uuidv7()) RETURNING id INTO job;
    BEGIN
        INSERT INTO report_jobs(operation_id,owner_id) VALUES (op,uuidv7());
        RAISE EXCEPTION 'duplicate operation'; EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        UPDATE report_jobs SET status='ready' WHERE id=job;
        RAISE EXCEPTION 'ready without file'; EXCEPTION WHEN check_violation THEN NULL;
    END;
    INSERT INTO report_snapshots VALUES (job,uuidv7(),1,'v1','ru','test-key','\xabcdef');
    BEGIN
        UPDATE report_snapshots SET template_version='v2' WHERE job_id=job;
        RAISE EXCEPTION 'modified snapshot'; EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    UPDATE report_jobs SET status='ready',file_id=uuidv7() WHERE id=job;
END $$;
