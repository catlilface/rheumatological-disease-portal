// Package archive stores durable patient data on the single-writer BFF volume.
package archive

import (
	"encoding/json"
	"fmt"
	"time"

	bolt "go.etcd.io/bbolt"
	"portal/bff/internal/domain"
)

type Store struct{ *bolt.DB }

func Open(path string) (*Store, error) {
	db, err := bolt.Open(path, 0600, &bolt.Options{Timeout: time.Second})
	if err != nil {
		return nil, err
	}
	return &Store{db}, nil
}
func resultKey(ref domain.ResultRef) []byte {
	return []byte(fmt.Sprintf("%s/%020d", ref.ID, ref.Version))
}
func put(tx *bolt.Tx, bucket string, key []byte, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	b, err := tx.CreateBucketIfNotExists([]byte(bucket))
	if err != nil {
		return err
	}
	return b.Put(key, data)
}
func get(tx *bolt.Tx, bucket string, key []byte) []byte {
	if b := tx.Bucket([]byte(bucket)); b != nil {
		return b.Get(key)
	}
	return nil
}
func loadCabinet(tx *bolt.Tx, owner string) (*domain.Cabinet, error) {
	c := domain.NewCabinet()
	if data := get(tx, "cabinets", []byte(owner)); data != nil {
		return c, json.Unmarshal(data, c)
	}
	return c, nil
}
func (s *Store) Cabinet(owner string) (*domain.Cabinet, error) {
	var c *domain.Cabinet
	err := s.View(func(tx *bolt.Tx) error {
		var err error
		c, err = loadCabinet(tx, owner)
		return err
	})
	return c, err
}
func (s *Store) SaveResult(owner string, r domain.Result) error {
	return s.Update(func(tx *bolt.Tx) error { return put(tx, "results/"+owner, resultKey(r.ResultRef), r) })
}
func (s *Store) Result(owner string, ref domain.ResultRef) (domain.Result, error) {
	var r domain.Result
	err := s.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("results/" + owner))
		if b != nil {
			if data := b.Get(resultKey(ref)); data != nil {
				return json.Unmarshal(data, &r)
			}
		}
		return domain.NotFound()
	})
	return r, err
}
func (s *Store) History(owner string, w domain.Window) (domain.Page[domain.Result], error) {
	page := domain.Paginate([]domain.Result{}, w)
	err := s.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("results/" + owner))
		if b == nil {
			return nil
		}
		c := b.Cursor()
		for k, v := c.Last(); k != nil; k, v = c.Prev() {
			if page.Total >= w.Offset && len(page.Items) < w.Limit {
				var r domain.Result
				if err := json.Unmarshal(v, &r); err != nil {
					return err
				}
				page.Items = append(page.Items, r)
			}
			page.Total++
		}
		return nil
	})
	return page, err
}
