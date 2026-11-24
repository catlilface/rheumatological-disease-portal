DO $$ DECLARE material uuid; BEGIN
    INSERT INTO materials(kind,slug) VALUES ('doctor_route','fixture') RETURNING id INTO material;
    INSERT INTO material_versions(material_id,version,title,summary,body_markdown,author_id,reviewer_id,reviewed_at,status)
      SELECT material,n,'t','s','b',uuidv7(),uuidv7(),now(),'approved' FROM generate_series(1,2) AS n;
    UPDATE material_versions SET status='published' WHERE material_id=material AND version=1;
    BEGIN
        UPDATE material_versions SET status='published' WHERE material_id=material AND version=2;
        RAISE EXCEPTION 'two published versions'; EXCEPTION WHEN unique_violation THEN NULL;
    END;
END $$;
