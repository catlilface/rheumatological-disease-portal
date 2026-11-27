package delivery

import (
	"context"
	"database/sql"
	"errors"

	"github.com/google/uuid"
	"github.com/twmb/franz-go/pkg/kerr"
	"github.com/twmb/franz-go/pkg/kgo"
)

func (d *Delivery) PublishOne(ctx context.Context) (bool, error) {
	var handled bool
	err := transact(ctx, d.db, func(tx *sql.Tx) error {
		if err := lock(ctx, tx, "kafka:publish"); err != nil {
			return err
		}

		var id uuid.UUID
		var topic, key string
		var payload, header []byte
		err := tx.QueryRowContext(ctx, `
			SELECT id, topic, entity_key, payload, metadata
			FROM public.kafka_outbox AS pending
			WHERE pending.published_at IS NULL AND pending.quarantined_at IS NULL
			  AND NOT EXISTS (
			      SELECT 1 FROM public.kafka_outbox AS blocked
			      WHERE blocked.quarantined_at IS NOT NULL AND blocked.topic = pending.topic
			        AND blocked.entity_key = pending.entity_key AND blocked.position < pending.position
			  )
			ORDER BY pending.position LIMIT 1`).Scan(&id, &topic, &key, &payload, &header)
		if errors.Is(err, sql.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}

		record := &kgo.Record{Topic: topic, Key: []byte(key), Value: payload}
		if header != nil {
			record.Headers = []kgo.RecordHeader{{Key: Header, Value: header}}
		}

		publish, cancel := context.WithTimeout(ctx, d.opts.PublishTimeout)
		defer cancel()
		err = d.broker.ProduceSync(publish, record).FirstErr()
		if err == nil {
			_, err = tx.ExecContext(ctx, `
				UPDATE public.kafka_outbox SET published_at = clock_timestamp() WHERE id = $1`, id)
		} else if code, ok := permanentError(err); ok {
			_, err = tx.ExecContext(ctx, `
				UPDATE public.kafka_outbox SET quarantined_at = clock_timestamp(), publish_error = $2
				WHERE id = $1`, id, code)
		}
		handled = err == nil
		return err
	})
	return handled && err == nil, err
}

func permanentError(err error) (int16, bool) {
	var kafkaErr *kerr.Error
	if !errors.As(err, &kafkaErr) {
		return 0, false
	}
	switch kafkaErr {
	case kerr.CorruptMessage, kerr.MessageTooLarge, kerr.RecordListTooLarge,
		kerr.TopicAuthorizationFailed, kerr.InvalidTopicException:
		return kafkaErr.Code, true
	default:
		return 0, false
	}
}
