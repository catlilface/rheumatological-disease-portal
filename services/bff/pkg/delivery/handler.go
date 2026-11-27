package delivery

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
)

func apply(ctx context.Context, tx *sql.Tx, message Message, handler Handler) (outcome, bool, error) {
	meta := message.Metadata
	var version int64
	err := tx.QueryRowContext(ctx, `
		SELECT version FROM public.kafka_versions WHERE kind = $1 AND entity_key = $2`,
		meta.Kind, meta.Key()).Scan(&version)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return outcome{}, false, err
	}
	if meta.Version <= version {
		if meta.Kind == Event {
			return outcome{Status: "stale"}, false, nil
		}
		return outcome{Error: "stale_version"}, false, nil
	}
	if meta.Kind == Command && meta.Version != version+1 {
		return outcome{Error: "version_gap"}, false, nil
	}
	if _, err = tx.ExecContext(ctx, "SAVEPOINT delivery_handler"); err != nil {
		return outcome{}, false, err
	}

	result, err := handler(ctx, tx, message)
	if err == nil {
		if result == nil {
			result = json.RawMessage("null")
		}
		_, err = tx.ExecContext(ctx, "SELECT $1::jsonb", string(result))
	}
	if err != nil {
		if ctx.Err() != nil {
			return outcome{}, false, ctx.Err()
		}
		if _, rollbackErr := tx.ExecContext(ctx, "ROLLBACK TO SAVEPOINT delivery_handler"); rollbackErr != nil {
			return outcome{}, false, rollbackErr
		}
		if errors.Is(err, ErrRejected) {
			return outcome{Error: "rejected"}, false, nil
		}
		return outcome{Error: "handler_failed"}, true, nil
	}
	if _, err := tx.ExecContext(ctx, "RELEASE SAVEPOINT delivery_handler"); err != nil {
		return outcome{}, false, err
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO public.kafka_versions (kind, entity_key, version) VALUES ($1, $2, $3)
		ON CONFLICT (kind, entity_key) DO UPDATE SET version = excluded.version`,
		meta.Kind, meta.Key(), meta.Version)
	return outcome{Status: "succeeded", Result: result}, false, err
}
