// Package memory implements the single-process demo repositories. One transaction covers
// authentication, aggregate mutation and the idempotency receipt, including cross-context reads.
package memory

import "sync"

type Store[K comparable, V any] map[K]V

func New[K comparable, V any]() Store[K, V] { return make(Store[K, V]) }
func (s Store[K, V]) Get(k K) (V, bool)     { v, ok := s[k]; return v, ok }
func (s Store[K, V]) Put(k K, v V)          { s[k] = v }
func (s Store[K, V]) Delete(k K)            { delete(s, k) }

type Transactions struct{ mu sync.Mutex }

func (t *Transactions) Within(f func()) { t.mu.Lock(); defer t.mu.Unlock(); f() }
