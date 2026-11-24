DO $$
DECLARE questionnaire uuid; session uuid; result uuid; history jsonb;
BEGIN
    INSERT INTO questionnaire_versions(survey_code,weights_version,disclaimer_version,definition)
      VALUES ('fixture','w1','d1','{}') RETURNING id INTO questionnaire;
    INSERT INTO screening_sessions(owner_id,questionnaire_version_id,disclaimer_accepted_at)
      VALUES (uuidv7(),questionnaire,now()) RETURNING id INTO session;
    BEGIN
        UPDATE screening_sessions SET questionnaire_version_id=uuidv7() WHERE id=session;
        RAISE EXCEPTION 'unpinned questionnaire'; EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO screening_answers VALUES (uuidv7(),'q','false',0);
        RAISE EXCEPTION 'orphan answer'; EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    INSERT INTO screening_answers VALUES (session,'q','true',1);
    BEGIN
        INSERT INTO screening_answers VALUES (session,'q','false',0);
        RAISE EXCEPTION 'second answer'; EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        UPDATE screening_sessions SET status='completed',final_result_id=uuidv7() WHERE id=session;
        SET CONSTRAINTS final_result_of_this_session IMMEDIATE;
        RAISE EXCEPTION 'completed without result'; EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    INSERT INTO screening_results(session_id,revisions) VALUES (session,'[{"level":"RED_FLAG","score":1}]') RETURNING id INTO result;
    BEGIN
        INSERT INTO screening_results(session_id,revisions) VALUES (session,'[{"level":"LOW"}]');
        RAISE EXCEPTION 'second result'; EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        UPDATE screening_results SET revisions=revisions || '[{"level":"LOW"}]' WHERE id=result;
        RAISE EXCEPTION 'downgraded red flag'; EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE screening_results SET revisions='[{"level":"LOW"},{"level":"RED_FLAG"}]' WHERE id=result;
        RAISE EXCEPTION 'changed historical version'; EXCEPTION WHEN check_violation THEN NULL;
    END;
    UPDATE screening_results SET revisions=revisions || '[{"level":"RED_FLAG","score":2}]' WHERE id=result RETURNING revisions INTO history;
    IF history->0->>'score' <> '1' OR history->1->>'score' <> '2' THEN RAISE EXCEPTION 'wrong exact version'; END IF;
    UPDATE screening_sessions SET status='completed',final_result_id=result WHERE id=session;
    BEGIN
        UPDATE screening_results SET revisions=revisions || '[{"level":"RED_FLAG"}]' WHERE id=result;
        RAISE EXCEPTION 'changed final result'; EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE screening_sessions SET status='in_progress',final_result_id=NULL WHERE id=session;
        RAISE EXCEPTION 'reopened completed session'; EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        DELETE FROM screening_results WHERE id=result;
        RAISE EXCEPTION 'deleted result'; EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
