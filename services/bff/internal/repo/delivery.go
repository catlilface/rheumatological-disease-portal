package repo

import (
	"context"
	"database/sql"
	"encoding/json"

	"github.com/google/uuid"

	"portal/bff/internal/models"
)

type DeliveryCounters struct{ DB *sql.DB }

func (r DeliveryCounters) Add(ctx context.Context, tx *sql.Tx, id uuid.UUID, delta int64) (int64, error) {
	var value int64
	err := tx.QueryRowContext(ctx, `
		INSERT INTO public.delivery_demo_counters (id, value) VALUES ($1, $2)
		ON CONFLICT (id) DO UPDATE SET value = delivery_demo_counters.value + excluded.value
		RETURNING value`, id, delta).Scan(&value)
	return value, err
}

func (r DeliveryCounters) Project(ctx context.Context, tx *sql.Tx, id uuid.UUID, value int64) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO public.delivery_demo_projection (id, value) VALUES ($1, $2)
		ON CONFLICT (id) DO UPDATE SET value = excluded.value`, id, value)
	return err
}

func (r DeliveryCounters) Counter(ctx context.Context, id uuid.UUID) (models.CounterView, error) {
	var view models.CounterView
	err := r.DB.QueryRowContext(ctx, `
		SELECT (SELECT value FROM public.delivery_demo_counters WHERE id = $1),
		       (SELECT value FROM public.delivery_demo_projection WHERE id = $1)`, id).Scan(&view.Value, &view.Projected)
	return view, err
}

func (r DeliveryCounters) Outbox(ctx context.Context, key string) (json.RawMessage, error) {
	var rows []byte
	err := r.DB.QueryRowContext(ctx, `
		SELECT COALESCE(jsonb_agg(jsonb_build_object(
			'id', id, 'topic', topic, 'published_at', published_at,
			'quarantined_at', quarantined_at, 'publish_error', publish_error) ORDER BY position), '[]')
		FROM public.kafka_outbox WHERE entity_key = $1`, key).Scan(&rows)
	return rows, err
}
