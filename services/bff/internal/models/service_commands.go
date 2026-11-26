package models

import "portal/bff/pkg/idempotency"

type OperationKey struct{ Actor, Owner, ID string }

type IntentKey struct{ Actor, Key string }

type Receipt struct {
	Fingerprint idempotency.Fingerprint
	Operation   OperationKey
}
