package archive

import (
	"encoding/json"

	bolt "go.etcd.io/bbolt"

	"portal/bff/internal/models"
	"portal/bff/pkg/idempotency"
)

// A committed intent always points to a committed operation and cabinet snapshot.
// A rejected operation has a receipt but must not overwrite the cabinet.
func (s *Store) RunCabinet(actor, key string, fp idempotency.Fingerprint, execute func(*models.Cabinet) (models.Operation, error)) (models.OperationKey, error) {
	var id models.OperationKey
	err := s.Update(func(tx *bolt.Tx) error {
		intents := "cabinet-intents/" + actor
		if data := get(tx, intents, []byte(key)); data != nil {
			var receipt models.Receipt
			if err := json.Unmarshal(data, &receipt); err != nil {
				return err
			}
			var err error
			id, err = receipt.Replay(fp)
			return err
		}
		c, err := loadCabinet(tx, actor)
		if err != nil {
			return err
		}
		op, err := execute(c)
		if err != nil {
			return err
		}
		if op.State == "succeeded" {
			if err := put(tx, "cabinets", []byte(actor), c); err != nil {
				return err
			}
		}
		if err := put(tx, "cabinet-ops/"+actor, []byte(op.ID), op); err != nil {
			return err
		}
		id = models.OperationKey{Actor: actor, Owner: "cabinet", ID: op.ID}
		return put(tx, intents, []byte(key), models.Receipt{Fingerprint: fp, Operation: id})
	})
	return id, err
}

func (s *Store) HasCabinetIntent(actor, key string) (bool, error) {
	var used bool
	err := s.View(func(tx *bolt.Tx) error { used = get(tx, "cabinet-intents/"+actor, []byte(key)) != nil; return nil })
	return used, err
}

func (s *Store) CabinetOperation(actor, id string) (models.Operation, error) {
	var op models.Operation
	err := s.View(func(tx *bolt.Tx) error {
		data := get(tx, "cabinet-ops/"+actor, []byte(id))
		if data == nil {
			return models.NotFound()
		}
		return json.Unmarshal(data, &op)
	})
	return op, err
}
