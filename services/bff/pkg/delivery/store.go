package delivery

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Handler func(context.Context, *sql.Tx, Message) (json.RawMessage, error)

type Broker interface {
	ProduceSync(context.Context, ...*kgo.Record) kgo.ProduceResults
}

type Options struct {
	DeadLetterTopic string
	MaxAttempts     int
	RetryDelay      time.Duration
	PublishTimeout  time.Duration
}

type Delivery struct {
	db     *sql.DB
	broker Broker
	opts   Options
}

func New(db *sql.DB, broker Broker, opts Options) (*Delivery, error) {
	if db == nil || broker == nil || !ValidTopic(opts.DeadLetterTopic) ||
		opts.MaxAttempts < 1 || opts.RetryDelay < 0 || opts.PublishTimeout <= 0 {
		return nil, errors.New("invalid delivery configuration")
	}
	return &Delivery{db: db, broker: broker, opts: opts}, nil
}

func transact(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func lock(ctx context.Context, tx *sql.Tx, key string) error {
	_, err := tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", key)
	return err
}

func (d *Delivery) Submit(ctx context.Context, message Message) error {
	return transact(ctx, d.db, func(tx *sql.Tx) error {
		return Enqueue(ctx, tx, message)
	})
}

func Enqueue(ctx context.Context, tx *sql.Tx, message Message) error {
	if err := message.validate(); err != nil {
		return err
	}
	meta := message.Metadata
	header, err := json.Marshal(meta)
	if err != nil {
		return err
	}
	if err = lock(ctx, tx, "kafka:outbox:"+meta.Key()); err != nil {
		return err
	}
	result, err := tx.ExecContext(ctx, `
		INSERT INTO public.kafka_outbox (id, topic, entity_key, payload, metadata)
		VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING`,
		meta.ID, message.Topic, meta.Key(), message.Payload, header)
	if err != nil {
		return err
	}
	if count, err := result.RowsAffected(); err != nil || count == 1 {
		return err
	}
	var topic, key string
	var payload, metadata []byte
	err = tx.QueryRowContext(ctx, `
		SELECT topic, entity_key, payload, metadata FROM public.kafka_outbox WHERE id = $1`,
		meta.ID).Scan(&topic, &key, &payload, &metadata)
	if err != nil {
		return err
	}
	if topic != message.Topic || key != meta.Key() ||
		!bytes.Equal(payload, message.Payload) || !bytes.Equal(metadata, header) {
		return ErrConflict
	}
	return nil
}

func (d *Delivery) Operation(ctx context.Context, id uuid.UUID) (json.RawMessage, error) {
	var outcome []byte
	err := d.db.QueryRowContext(ctx, "SELECT outcome FROM public.kafka_operations WHERE id = $1", id).Scan(&outcome)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	return outcome, err
}

func (d *Delivery) deadLetter(ctx context.Context, tx *sql.Tx, record *kgo.Record, code string) error {
	key := fmt.Sprintf("%s:%d:%d", record.Topic, record.Partition, record.Offset)
	payload, err := json.Marshal(struct {
		Topic     string `json:"topic"`
		Partition int32  `json:"partition"`
		Offset    int64  `json:"offset"`
		Code      string `json:"code"`
	}{record.Topic, record.Partition, record.Offset, code})
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO public.kafka_outbox (id, topic, entity_key, payload)
		VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING`,
		uuid.NewSHA1(uuid.NameSpaceURL, []byte("kafka:"+key)), d.opts.DeadLetterTopic, key, payload)
	return err
}
