package service_test

import (
	"testing"
	"time"

	"github.com/google/uuid"

	"portal/bff/cmd/config"
	"portal/bff/internal/repo"
	app "portal/bff/internal/service"
	"portal/bff/pkg/credentials"
)

func identity(at *time.Time) app.Identity {
	defaults := config.Defaults()
	return app.Identity{
		Runtime: app.Runtime{
			ID:    uuid.NewString,
			Token: uuid.NewString,
			Now:   func() time.Time { return *at },
		},
		Access:         repo.New[string, *app.Login](),
		Refreshes:      repo.New[string, *app.Login](),
		Accounts:       repo.New[string, app.Account](),
		Retries:        repo.New[app.ReplayKey, *app.Login](),
		Passwords:      credentials.Scrypt{},
		SessionTTL:     defaults.Demo.SessionTTL,
		ModeratorEmail: defaults.Demo.ModeratorEmail,
	}
}

func TestRefreshRetriesCannotResurrectSession(t *testing.T) {
	now := time.Now()
	s := identity(&now)
	guest, err := s.Guest("g", "")
	if err != nil {
		t.Fatal(err)
	}
	rotated, err := s.Rotate(guest.Refresh, "r")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.Session(guest.Access); err == nil {
		t.Fatal("old access token accepted")
	}
	if _, err := s.Rotate(guest.Refresh, "another-key"); err == nil {
		t.Fatal("old refresh token accepted with new key")
	}
	if retry, err := s.Rotate(guest.Refresh, "r"); err != nil || retry != rotated {
		t.Fatal("retry did not return same login")
	}
	now = rotated.Expires
	if _, err := s.Rotate(guest.Refresh, "r"); err == nil {
		t.Fatal("expired replay succeeded")
	}
}

func TestRegistrationRetryRequiresCredentials(t *testing.T) {
	now := time.Now()
	s := identity(&now)
	email, password := "alice@example.test", "synthetic-password"
	consent := app.MedicalConsent{Version: app.PolicyVersion}
	if _, err := s.Register("key", email, password, consent); err == nil {
		t.Fatal("missing explicit consent")
	}
	consent.Accepted = true
	l, err := s.Register("key", email, password, consent)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Register("key", email, "different", consent); err == nil {
		t.Fatal("retry without password succeeded")
	}
	if got, e := s.Register("key", email, password, consent); e != nil || got != l {
		t.Fatal("legitimate retry failed")
	}
	s.Revoke(l)
	if _, err = s.Register("key", email, password, consent); err == nil {
		t.Fatal("revoked session replayed")
	}
	if _, err = s.Register("m", "moderator@example.test", "x", consent); err == nil {
		t.Fatal("allowed registration of staff account")
	}
	if _, err = s.SignIn("moderator@example.test", ""); err == nil {
		t.Fatal("moderation enabled without a password")
	}
}
