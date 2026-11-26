package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"portal/bff/internal/models"
	"strings"

	"github.com/google/uuid"

	"portal/bff/pkg/delivery"
)

const (
	demoStream          = "demo-counter"
	oversizedEventBytes = 2 << 20
	increment           = "increment"
	retryAction         = "retry"
	rejectAction        = "reject"
	invalidOutcome      = "invalid_outcome"
	oversizedEvent      = "oversized_event"
)

var ErrInvalidDeliveryCommand = errors.New("invalid delivery command")

type CounterWriter interface {
	Add(context.Context, *sql.Tx, uuid.UUID, int64) (int64, error)
	Project(context.Context, *sql.Tx, uuid.UUID, int64) error
}

type DeliveryDemo struct {
	Transport                *delivery.Delivery
	Counters                 CounterWriter
	CommandTopic, EventTopic string
}

type CounterCommand = models.CounterCommand

type CounterChange = models.CounterChange

type counterUpdated = models.CounterUpdated

func (s DeliveryDemo) Submit(ctx context.Context, command CounterCommand) error {
	switch command.Action {
	case increment, retryAction, rejectAction, invalidOutcome, oversizedEvent:
	default:
		return ErrInvalidDeliveryCommand
	}
	if command.MessageID == uuid.Nil || command.OperationID == uuid.Nil ||
		command.EntityID == uuid.Nil || command.Version < 1 || command.Delta == 0 {
		return ErrInvalidDeliveryCommand
	}
	payload, err := json.Marshal(command.CounterChange)
	if err != nil {
		return err
	}
	return s.Transport.Submit(ctx, delivery.Message{
		Topic: s.CommandTopic, Payload: payload,
		Metadata: delivery.Metadata{
			ID: command.MessageID, OperationID: command.OperationID, EntityID: command.EntityID,
			Version: command.Version, Stream: demoStream, Kind: delivery.Command,
		},
	})
}

func CounterKey(id uuid.UUID) string {
	return (delivery.Metadata{Stream: demoStream, EntityID: id}).Key()
}

func (s DeliveryDemo) ApplyCommand(ctx context.Context, tx *sql.Tx, msg delivery.Message) (json.RawMessage, error) {
	var change CounterChange
	meta := msg.Metadata
	if msg.Topic != s.CommandTopic || meta.Stream != demoStream || meta.Kind != delivery.Command ||
		json.Unmarshal(msg.Payload, &change) != nil || change.Delta == 0 {
		return nil, delivery.ErrRejected
	}
	switch change.Action {
	case rejectAction:
		return nil, delivery.ErrRejected
	case increment, retryAction, invalidOutcome, oversizedEvent:
	default:
		return nil, delivery.ErrRejected
	}
	value, err := s.Counters.Add(ctx, tx, meta.EntityID, change.Delta)
	if err != nil {
		return nil, err
	}
	event := counterUpdated{Value: value}
	if change.Action == oversizedEvent {
		event.Padding = strings.Repeat("x", oversizedEventBytes)
	}
	payload, err := json.Marshal(event)
	if err != nil {
		return nil, err
	}
	meta.ID, meta.Kind = uuid.New(), delivery.Event
	if err := delivery.Enqueue(ctx, tx, delivery.Message{Topic: s.EventTopic, Metadata: meta, Payload: payload}); err != nil {
		return nil, err
	}
	switch change.Action {
	case retryAction:
		return nil, errors.New("synthetic handler failure")
	case invalidOutcome:
		return json.RawMessage(`"\u0000"`), nil
	default:
		return json.Marshal(counterUpdated{Value: value})
	}
}

func (s DeliveryDemo) ApplyEvent(ctx context.Context, tx *sql.Tx, msg delivery.Message) (json.RawMessage, error) {
	var event counterUpdated
	if msg.Topic != s.EventTopic || msg.Metadata.Stream != demoStream || msg.Metadata.Kind != delivery.Event ||
		json.Unmarshal(msg.Payload, &event) != nil {
		return nil, delivery.ErrRejected
	}
	return nil, s.Counters.Project(ctx, tx, msg.Metadata.EntityID, event.Value)
}
