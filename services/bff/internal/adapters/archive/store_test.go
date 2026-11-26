package archive

import (
	"path/filepath"
	"portal/bff/internal/domain"
	"testing"
)

func TestOperationWriteFailureRollsBackCabinetAndIntent(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "archive.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	_, err = s.RunCabinet("alice", "key", [32]byte{}, func(c *domain.Cabinet) (domain.Operation, error) {
		// bbolt rejects the empty operation key after the snapshot has been written.
		return domain.Operation{State: "succeeded"}, c.SetReminders(domain.ReminderSettings{Timezone: "Europe/Moscow"})
	})
	if err == nil {
		t.Fatal("operation write should fail")
	}
	if used, err := s.HasCabinetIntent("alice", "key"); err != nil || used {
		t.Fatal("partial receipt", err)
	}
	if c, err := s.Cabinet("alice"); err != nil || c.Reminders().Timezone != "UTC" {
		t.Fatal("partial cabinet update", err)
	}
}

func TestPatientHistoryAndCabinetSurviveRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "archive.db")
	open := func() *Store {
		t.Helper()
		s, err := Open(path)
		if err != nil {
			t.Fatal(err)
		}
		return s
	}
	s := open()
	if _, err := s.RunCabinet("alice", "key", [32]byte{}, func(c *domain.Cabinet) (domain.Operation, error) {
		return domain.Operation{ID: "op", State: "succeeded"}, c.SetReminders(domain.ReminderSettings{Timezone: "Europe/Moscow"})
	}); err != nil {
		t.Fatal(err)
	}
	for _, version := range []int{1, 2} {
		if err := s.SaveResult("alice", domain.Result{ResultRef: domain.ResultRef{ID: "result", Version: version}}); err != nil {
			t.Fatal(err)
		}
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = open()
	defer s.Close()
	c, err := s.Cabinet("alice")
	if err != nil || c.Reminders().Timezone != "Europe/Moscow" {
		t.Fatal("lost cabinet", err)
	}
	for _, owner := range []string{"alice", "bob"} {
		p, err := s.History(owner, domain.Window{Limit: 1})
		if err != nil {
			t.Fatal(err)
		}
		if owner == "bob" {
			if p.Total != 0 {
				t.Fatal("history leak")
			}
			if _, err := s.Result(owner, domain.ResultRef{ID: "result", Version: 1}); err == nil {
				t.Fatal("exact result leak")
			}
		} else if p.Total != 2 || len(p.Items) != 1 || p.Items[0].Version != 2 {
			t.Fatal("lost versions", p)
		}
	}
}
