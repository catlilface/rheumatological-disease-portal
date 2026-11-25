package application

import "time"

// Store is an outbound port. Keys of private aggregates always include their owner.
// Mutable aggregates may only be accessed inside the same UnitOfWork.
type Store[K comparable, V any] interface {
	Get(K) (V, bool)
	Put(K, V)
	Delete(K)
}
type UnitOfWork interface{ Within(func()) }
type Runtime struct {
	Now   func() time.Time
	ID    func() string
	Token func() string
}
