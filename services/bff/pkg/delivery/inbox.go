package delivery

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Consumer interface {
	PollRecords(context.Context, int) kgo.Fetches
	CommitRecords(context.Context, ...*kgo.Record) error
	AllowRebalance()
}

func (d *Delivery) ConsumeOne(ctx context.Context, consumer Consumer, handler Handler) error {
	fetches := consumer.PollRecords(ctx, 1)
	defer consumer.AllowRebalance()
	if err := fetches.Err(); err != nil {
		return err
	}
	iter := fetches.RecordIter()
	if iter.Done() {
		return nil
	}
	record := iter.Next()
	if err := d.Process(ctx, record, handler); err != nil {
		return err
	}
	return consumer.CommitRecords(ctx, record)
}

func (d *Delivery) Process(ctx context.Context, record *kgo.Record, handler Handler) error {
	message, err := decode(record)
	if err != nil {
		return transact(ctx, d.db, func(tx *sql.Tx) error {
			return d.deadLetter(ctx, tx, record, "invalid_message")
		})
	}

	for {
		var retry bool
		err := transact(ctx, d.db, func(tx *sql.Tx) error {
			var err error
			retry, err = d.attempt(ctx, tx, record, message, handler)
			return err
		})
		if err != nil || !retry {
			return err
		}
		if err := wait(ctx, d.opts.RetryDelay); err != nil {
			return err
		}
	}
}

func wait(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

type receipt struct {
	fingerprint []byte
	attempts    int
	outcome     json.RawMessage
}

func readReceipt(ctx context.Context, tx *sql.Tx, kind string, id uuid.UUID) (receipt, error) {
	query := "SELECT fingerprint, attempts, outcome FROM public.kafka_inbox WHERE id = $1"
	if kind == Command {
		query = "SELECT fingerprint, attempts, outcome FROM public.kafka_operations WHERE id = $1"
	}
	var row receipt
	var encoded []byte
	err := tx.QueryRowContext(ctx, query, id).Scan(&row.fingerprint, &row.attempts, &encoded)
	row.outcome = encoded
	return row, err
}

type outcome struct {
	Status string          `json:"status,omitempty"`
	Result json.RawMessage `json:"result,omitempty"`
	Error  string          `json:"error,omitempty"`
}

func (d *Delivery) attempt(
	ctx context.Context, tx *sql.Tx, record *kgo.Record, message Message, handler Handler,
) (bool, error) {
	meta, fingerprint := message.Metadata, message.fingerprint()
	if err := lock(ctx, tx, "kafka:message:"+meta.ID.String()); err != nil {
		return false, err
	}

	inbox, err := readReceipt(ctx, tx, Event, meta.ID)
	switch {
	case errors.Is(err, sql.ErrNoRows):
		_, err = tx.ExecContext(ctx,
			"INSERT INTO public.kafka_inbox (id, fingerprint) VALUES ($1, $2)", meta.ID, fingerprint)
		if err != nil {
			return false, err
		}
	case err != nil:
		return false, err
	case !bytes.Equal(inbox.fingerprint, fingerprint):
		return false, d.deadLetter(ctx, tx, record, "idempotency_conflict")
	case inbox.outcome != nil:
		return false, nil
	}

	attempts := inbox.attempts
	if meta.Kind == Command {
		if err := lock(ctx, tx, "kafka:operation:"+meta.OperationID.String()); err != nil {
			return false, err
		}
		operation, err := readReceipt(ctx, tx, Command, meta.OperationID)
		switch {
		case errors.Is(err, sql.ErrNoRows):
			_, err = tx.ExecContext(ctx,
				"INSERT INTO public.kafka_operations (id, fingerprint) VALUES ($1, $2)",
				meta.OperationID, fingerprint)
			if err != nil {
				return false, err
			}
		case err != nil:
			return false, err
		case !bytes.Equal(operation.fingerprint, fingerprint):
			encoded, err := d.outcome(ctx, tx, record, outcome{Error: "idempotency_conflict"})
			if err != nil {
				return false, err
			}
			return false, writeInbox(ctx, tx, meta.ID, attempts, encoded)
		case operation.outcome != nil:
			return false, writeInbox(ctx, tx, meta.ID, attempts, operation.outcome)
		default:
			attempts = operation.attempts
		}
	}
	if err := lock(ctx, tx, "kafka:entity:"+meta.Key()); err != nil {
		return false, err
	}

	value, retry, err := apply(ctx, tx, message, handler)
	if err != nil {
		return false, err
	}
	attempts++
	retry = retry && attempts < d.opts.MaxAttempts

	var encoded json.RawMessage
	if !retry {
		encoded, err = d.outcome(ctx, tx, record, value)
		if err != nil {
			return false, err
		}
	}
	if err := writeInbox(ctx, tx, meta.ID, attempts, encoded); err != nil {
		return false, err
	}
	if meta.Kind == Command {
		_, err = tx.ExecContext(ctx, `
			UPDATE public.kafka_operations SET attempts = $2, outcome = $3::jsonb WHERE id = $1`,
			meta.OperationID, attempts, nullableJSON(encoded))
	}
	return retry, err
}

func writeInbox(ctx context.Context, tx *sql.Tx, id uuid.UUID, attempts int, encoded json.RawMessage) error {
	_, err := tx.ExecContext(ctx, `
		UPDATE public.kafka_inbox SET attempts = $2, outcome = $3::jsonb WHERE id = $1`,
		id, attempts, nullableJSON(encoded))
	return err
}

func nullableJSON(encoded json.RawMessage) sql.NullString {
	return sql.NullString{String: string(encoded), Valid: encoded != nil}
}

func (d *Delivery) outcome(ctx context.Context, tx *sql.Tx, record *kgo.Record, value outcome) (json.RawMessage, error) {
	if value.Error != "" {
		if err := d.deadLetter(ctx, tx, record, value.Error); err != nil {
			return nil, err
		}
	}
	return json.Marshal(value)
}
