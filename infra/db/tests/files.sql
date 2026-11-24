DO $$ DECLARE file uuid; subject uuid := uuidv7(); BEGIN
    INSERT INTO stored_files(object_key,owner_id,report_id,source_result_id,source_result_version,filename,media_type,size_bytes,sha256)
      VALUES ('fixture',subject,uuidv7(),uuidv7(),1,'test.pdf','application/pdf',4,sha256('test')) RETURNING id INTO file;
    INSERT INTO download_grants(file_id,subject_id,token_hash,expires_at) VALUES (file,subject,sha256('fixture'),now()+interval '5 min');
    BEGIN
        INSERT INTO download_grants(file_id,subject_id,token_hash,expires_at) VALUES (uuidv7(),subject,sha256('other'),now()+interval '5 min');
        RAISE EXCEPTION 'orphan grant'; EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
END $$;
