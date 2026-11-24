DO $$ DECLARE article uuid := uuidv7(); BEGIN
    INSERT INTO article_projection(article_id,version,published,snapshot) VALUES (article,1,true,'{}');
    UPDATE article_projection SET version=2, deleted=true, published=false, snapshot=NULL WHERE article_id=article;
    BEGIN
        UPDATE article_projection SET version=1, deleted=false, published=true, snapshot='{}' WHERE article_id=article;
        RAISE EXCEPTION 'resurrected stale article'; EXCEPTION WHEN check_violation THEN NULL;
    END;
END $$;
