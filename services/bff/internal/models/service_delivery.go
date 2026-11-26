package models

import "github.com/google/uuid"

type CounterCommand struct {
	MessageID   uuid.UUID `json:"message_id"`
	OperationID uuid.UUID `json:"operation_id"`
	EntityID    uuid.UUID `json:"entity_id"`
	Version     int64     `json:"version"`
	CounterChange
}

type CounterChange struct {
	Action string `json:"action"`
	Delta  int64  `json:"delta"`
}

type CounterUpdated struct {
	Value   int64  `json:"value"`
	Padding string `json:"padding,omitempty"`
}
