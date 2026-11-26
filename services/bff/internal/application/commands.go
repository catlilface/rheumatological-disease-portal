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

func (r Receipt) Replay(fingerprint [32]byte) (OperationKey, error) {
	if fingerprint != r.Fingerprint {
		return OperationKey{}, domain.Fail(domain.Conflict, "IDEMPOTENCY_KEY_REUSED")
	}
	return r.Operation, nil
}

type CabinetJournal interface {
	RunCabinet(actor, key string, fingerprint [32]byte, execute func(*domain.Cabinet) (domain.Operation, error)) (OperationKey, error)
	HasCabinetIntent(actor, key string) (bool, error)
	CabinetOperation(actor, id string) (domain.Operation, error)
}

type Commands struct {
	Runtime
	Journal    CabinetJournal
	Operations Store[OperationKey, domain.Operation]
	Receipts   Store[IntentKey, Receipt]
}

func (s Commands) Run(actor, owner, key string, fingerprint [32]byte, apply func() ([]domain.Resource, error)) (OperationKey, error) {
	intent := IntentKey{actor, key}
	if r, ok := s.Receipts.Get(intent); ok {
		return r.Replay(fingerprint)
	}
	if s.Journal != nil {
		used, err := s.Journal.HasCabinetIntent(actor, key)
		if err != nil {
			return OperationKey{}, err
		}
		if used {
			return OperationKey{}, domain.Fail(domain.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
	}
	op, err := s.execute(apply)
	if err != nil {
		return OperationKey{}, err
	}
	id := OperationKey{actor, owner, op.ID}
	s.Operations.Put(id, op)
	s.Receipts.Put(intent, Receipt{fingerprint, id})
	return id, nil
}

func (s Commands) RunCabinet(a *domain.Actor, key string, fp [32]byte, cabinets Cabinets, apply func(PatientCabinet) ([]domain.Resource, error)) (OperationKey, error) {
	if err := a.RequirePatient(); err != nil {
		return OperationKey{}, err
	}
	if s.Journal == nil {
		return s.Run(a.ID, "cabinet", key, fp, func() ([]domain.Resource, error) {
			p, err := cabinets.For(a)
			if err != nil {
				return nil, err
			}
			return apply(p)
		})
	}
	if _, used := s.Receipts.Get(IntentKey{a.ID, key}); used {
		return OperationKey{}, domain.Fail(domain.Conflict, "IDEMPOTENCY_KEY_REUSED")
	}
	return s.Journal.RunCabinet(a.ID, key, fp, func(record *domain.Cabinet) (domain.Operation, error) {
		return s.execute(func() ([]domain.Resource, error) { return apply(PatientCabinet{record, s.Runtime}) })
	})
}

func (s Commands) execute(apply func() ([]domain.Resource, error)) (domain.Operation, error) {
	op := domain.Operation{ID: s.ID(), UpdatedAt: s.Now(), State: "succeeded", Resources: []domain.Resource{}}
	rs, err := apply()
	if err != nil {
		if !errors.As(err, &op.Error) {
			return domain.Operation{}, err
		}
		op.State = "rejected"
	} else if rs != nil {
		op.Resources = rs
	}
	return op, nil
}
func (s Commands) Get(a *domain.Actor, owner, id string) (domain.Operation, error) {
	if owner == "cabinet" && !a.Consent {
		return domain.Operation{}, domain.Fail(domain.Forbidden, "CONSENT_REQUIRED")
	}
	if owner == "cabinet" && s.Journal != nil {
		return s.Journal.CabinetOperation(a.ID, id)
	}
	op, ok := s.Operations.Get(OperationKey{a.ID, owner, id})
	if !ok {
		return op, domain.NotFound()
	}
	return op, nil
}
