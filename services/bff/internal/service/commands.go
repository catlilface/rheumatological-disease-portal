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

type CabinetJournal interface {
	RunCabinet(actor, key string, fingerprint idempotency.Fingerprint, execute func(*models.Cabinet) (models.Operation, error)) (OperationKey, error)
	HasCabinetIntent(actor, key string) (bool, error)
	CabinetOperation(actor, id string) (models.Operation, error)
}

type Commands struct {
	Runtime
	Journal    CabinetJournal
	Operations Store[OperationKey, models.Operation]
	Receipts   Store[IntentKey, Receipt]
}

func (s Commands) Run(actor, owner, key string, fingerprint idempotency.Fingerprint, apply func() ([]models.Resource, error)) (OperationKey, error) {
	intent := IntentKey{Actor: actor, Key: key}
	if r, ok := s.Receipts.Get(intent); ok {
		return r.Replay(fingerprint)
	}
	if s.Journal != nil {
		used, err := s.Journal.HasCabinetIntent(actor, key)
		if err != nil {
			return OperationKey{}, err
		}
		if used {
			return OperationKey{}, models.Fail(models.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
	}
	op, err := s.execute(apply)
	if err != nil {
		return OperationKey{}, err
	}
	id := OperationKey{Actor: actor, Owner: owner, ID: op.ID}
	s.Operations.Put(id, op)
	s.Receipts.Put(intent, Receipt{Fingerprint: fingerprint, Operation: id})
	return id, nil
}

func (s Commands) RunCabinet(a *models.Actor, key string, fp idempotency.Fingerprint, cabinets Cabinets, apply func(PatientCabinet) ([]models.Resource, error)) (OperationKey, error) {
	if err := a.RequirePatient(); err != nil {
		return OperationKey{}, err
	}
	if s.Journal == nil {
		return s.Run(a.ID, OwnerCabinet, key, fp, func() ([]models.Resource, error) {
			p, err := cabinets.For(a)
			if err != nil {
				return nil, err
			}
			return apply(p)
		})
	}
	if _, used := s.Receipts.Get(IntentKey{Actor: a.ID, Key: key}); used {
		return OperationKey{}, models.Fail(models.Conflict, "IDEMPOTENCY_KEY_REUSED")
	}
	return s.Journal.RunCabinet(a.ID, key, fp, func(record *models.Cabinet) (models.Operation, error) {
		return s.execute(func() ([]models.Resource, error) { return apply(PatientCabinet{record, s.Runtime}) })
	})
}

func (s Commands) execute(apply func() ([]models.Resource, error)) (models.Operation, error) {
	op := models.Operation{ID: s.ID(), UpdatedAt: s.Now(), State: operationSucceeded, Resources: []models.Resource{}}
	rs, err := apply()
	if err != nil {
		if !errors.As(err, &op.Error) {
			return models.Operation{}, err
		}
		op.State = operationRejected
	} else if rs != nil {
		op.Resources = rs
	}
	return op, nil
}

func (s Commands) Get(a *models.Actor, owner, id string) (models.Operation, error) {
	if owner == OwnerCabinet && !a.Consent {
		return models.Operation{}, models.Fail(models.Forbidden, "CONSENT_REQUIRED")
	}
	if owner == OwnerCabinet && s.Journal != nil {
		return s.Journal.CabinetOperation(a.ID, id)
	}
	op, ok := s.Operations.Get(OperationKey{Actor: a.ID, Owner: owner, ID: id})
	if !ok {
		return op, models.NotFound()
	}
	return op, nil
}
