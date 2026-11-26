package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"

	"portal/bff/internal/models"
	"portal/bff/internal/service"
	"portal/bff/pkg/delivery"
)

type DeliveryDemo interface {
	Submit(context.Context, service.CounterCommand) error
}

type DeliveryQueries interface {
	Operation(context.Context, uuid.UUID) (json.RawMessage, error)
}

type CounterQueries interface {
	Counter(context.Context, uuid.UUID) (models.CounterView, error)
	Outbox(context.Context, string) (json.RawMessage, error)
}

func (a *API) Delivery(demo DeliveryDemo, operations DeliveryQueries, counters CounterQueries) {
	const base = "/_demo/delivery"
	a.mux.HandleFunc("POST "+base+"/commands", func(w http.ResponseWriter, r *http.Request) {
		scheme := "http"
		if r.TLS != nil {
			scheme = "https"
		}
		if r.Header.Get("Origin") != scheme+"://"+r.Host ||
			r.Header.Get(portalRequestHeader) != portalRequestMarker {
			writeJSON(w, http.StatusForbidden, map[string]string{"code": "unsafe_request"})
			return
		}
		raw, _, err := readBody(w, r, a.cfg.HTTP.MaxBodyBytes)
		if err != nil {
			problem(w, err)
			return
		}
		var command service.CounterCommand
		if err := json.Unmarshal(raw, &command); err != nil {
			problem(w, invalid("body"))
			return
		}
		switch err := demo.Submit(r.Context(), command); {
		case errors.Is(err, service.ErrInvalidDeliveryCommand):
			problem(w, invalid("command"))
		case errors.Is(err, delivery.ErrConflict):
			writeJSON(w, http.StatusConflict, map[string]string{"code": "idempotency_conflict"})
		case err != nil:
			problem(w, err)
		default:
			writeJSON(w, http.StatusAccepted, map[string]uuid.UUID{"operation_id": command.OperationID})
		}
	})
	handle := func(path string, lookup func(context.Context, uuid.UUID) (json.RawMessage, error)) {
		a.mux.HandleFunc("GET "+base+path, func(w http.ResponseWriter, r *http.Request) {
			id, err := uuid.Parse(r.PathValue("id"))
			if err != nil || id == uuid.Nil {
				problem(w, invalid("id"))
				return
			}
			value, err := lookup(r.Context(), id)
			if err != nil {
				problem(w, err)
				return
			}
			if value == nil {
				writeJSON(w, http.StatusNotFound, map[string]string{"code": "outcome_unavailable"})
				return
			}
			writeJSON(w, http.StatusOK, value)
		})
	}
	handle("/operations/{id}", func(ctx context.Context, id uuid.UUID) (json.RawMessage, error) {
		value, err := operations.Operation(ctx, id)
		if value == nil {
			return nil, err
		}
		return value, err
	})
	handle("/counters/{id}", func(ctx context.Context, id uuid.UUID) (json.RawMessage, error) {
		value, err := counters.Counter(ctx, id)
		if err != nil {
			return nil, err
		}
		return json.Marshal(value)
	})
	handle("/counters/{id}/outbox", func(ctx context.Context, id uuid.UUID) (json.RawMessage, error) {
		return counters.Outbox(ctx, service.CounterKey(id))
	})
}
