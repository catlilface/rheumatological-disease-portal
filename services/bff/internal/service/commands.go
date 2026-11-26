package service

import (
	"errors"

	"portal/bff/internal/models"
	"portal/bff/pkg/idempotency"
)

const (
	OwnerScreening = "screening"
	OwnerCabinet   = "cabinet"
	OwnerCommunity = "community"
	OwnerReporting = "reporting"
	OwnerFiles     = "files"
	OwnerAI        = "ai"

	operationSucceeded = "succeeded"
	operationRejected  = "rejected"
)

type OperationKey = models.OperationKey
type IntentKey = models.IntentKey
type Receipt = models.Receipt

type Commands struct {
	Runtime
	Operations Store[OperationKey, models.Operation]
	Receipts   Store[IntentKey, Receipt]
}

func (s Commands) Run(actor, owner, key string, fingerprint idempotency.Fingerprint, apply func() ([]models.Resource, error)) (OperationKey, error) {
	intent := IntentKey{Actor: actor, Key: key}
	if r, ok := s.Receipts.Get(intent); ok {
		if fingerprint != r.Fingerprint {
			return OperationKey{}, models.Fail(models.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
		return r.Operation, nil
	}
	op := models.Operation{ID: s.ID(), UpdatedAt: s.Now(), State: operationSucceeded, Resources: []models.Resource{}}
	rs, err := apply()
	if err != nil {
		if !errors.As(err, &op.Error) {
			return OperationKey{}, err
		}
		op.State = operationRejected
	} else if rs != nil {
		op.Resources = rs
	}
	id := OperationKey{Actor: actor, Owner: owner, ID: op.ID}
	s.Operations.Put(id, op)
	s.Receipts.Put(intent, Receipt{Fingerprint: fingerprint, Operation: id})
	return id, nil
}

func (s Commands) Get(a *models.Actor, owner, id string) (models.Operation, error) {
	if owner == OwnerCabinet && !a.Consent {
		return models.Operation{}, models.Fail(models.Forbidden, "CONSENT_REQUIRED")
	}
	op, ok := s.Operations.Get(OperationKey{Actor: a.ID, Owner: owner, ID: id})
	if !ok {
		return op, models.NotFound()
	}
	return op, nil
}
