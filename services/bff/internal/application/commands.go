package application

import (
	"errors"

	"portal/bff/internal/domain"
)

type OperationKey struct{ Actor, Owner, ID string }
type IntentKey struct{ Actor, Key string }
type Receipt struct {
	Fingerprint [32]byte
	Operation   OperationKey
}
type Commands struct {
	Runtime
	Operations Store[OperationKey, domain.Operation]
	Receipts   Store[IntentKey, Receipt]
}

func (s Commands) Run(actor, owner, key string, fingerprint [32]byte, apply func() ([]domain.Resource, error)) (OperationKey, error) {
	intent := IntentKey{actor, key}
	if r, ok := s.Receipts.Get(intent); ok {
		if fingerprint != r.Fingerprint {
			return OperationKey{}, domain.Fail(domain.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
		return r.Operation, nil
	}
	op := domain.Operation{ID: s.ID(), UpdatedAt: s.Now(), State: "succeeded", Resources: []domain.Resource{}}
	rs, err := apply()
	if err != nil {
		if !errors.As(err, &op.Error) {
			return OperationKey{}, err
		}
		op.State = "rejected"
	} else if rs != nil {
		op.Resources = rs
	}
	id := OperationKey{actor, owner, op.ID}
	s.Operations.Put(id, op)
	s.Receipts.Put(intent, Receipt{fingerprint, id})
	return id, nil
}
func (s Commands) Get(a *domain.Actor, owner, id string) (domain.Operation, error) {
	if owner == "cabinet" && !a.Consent {
		return domain.Operation{}, domain.Fail(domain.Forbidden, "CONSENT_REQUIRED")
	}
	op, ok := s.Operations.Get(OperationKey{a.ID, owner, id})
	if !ok {
		return op, domain.NotFound()
	}
	return op, nil
}
