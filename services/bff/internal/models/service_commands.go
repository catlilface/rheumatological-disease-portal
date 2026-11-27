package models

import "portal/bff/pkg/idempotency"

type OperationKey struct{ Actor, Owner, ID string }

type IntentKey struct{ Actor, Key string }

type Receipt struct {
	Fingerprint idempotency.Fingerprint
	Operation   OperationKey
}

func (r Receipt) Replay(fingerprint idempotency.Fingerprint) (OperationKey, error) {
	if fingerprint != r.Fingerprint {
		return OperationKey{}, Fail(Conflict, "IDEMPOTENCY_KEY_REUSED")
	}
	return r.Operation, nil
}
