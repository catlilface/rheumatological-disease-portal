package archive

import (
	"path/filepath"
	"portal/bff/internal/domain"
	"testing"
)

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
	c := domain.NewCabinet()
	if err := c.SetReminders(domain.ReminderSettings{Timezone: "Europe/Moscow"}); err != nil {
		t.Fatal(err)
	}
	if err := s.SaveCabinet("alice", c); err != nil {
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
