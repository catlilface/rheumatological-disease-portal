package application

import (
	"crypto/subtle"
	"strings"
	"time"

	"portal/bff/internal/domain"
)

const PolicyVersion = "demo-medical-v1"
const moderatorEmail = "moderator@example.test"

type Login struct {
	Actor                  *domain.Actor
	Access, Refresh        string
	Expires, AccessExpires time.Time
	SessionID              string
	Roles                  []string
}
type Account struct {
	Actor *domain.Actor
	Hash  []byte
}
type Passwords interface {
	Hash(string) ([]byte, error)
	Matches([]byte, string) bool
}
type ReplayKey struct{ Scope, Key, Credential string }

// Identity is the in-memory fixture for the legacy browser contract tests.
// The BFF executable uses the gRPC IAM client instead.
type Identity struct {
	Runtime
	Access, Refreshes Store[string, *Login]
	Accounts          Store[string, Account]
	Retries           Store[ReplayKey, *Login]
	Passwords         Passwords
	ModeratorPassword string
}

func (s Identity) issue(a *domain.Actor) *Login {
	now := s.Now()
	roles := map[string][]string{"guest": {}, "member": {"patient"}, "staff": {"admin"}}
	l := &Login{Actor: a, SessionID: s.ID(), Access: s.Token(), Refresh: s.Token(), Expires: now.Add(30 * 24 * time.Hour), AccessExpires: now.Add(168 * time.Hour), Roles: roles[a.Kind]}
	s.Access.Put(l.Access, l)
	s.Refreshes.Put(l.Refresh, l)
	return l
}
func (s Identity) Session(cookie string) (*Login, error) {
	l, ok := s.Access.Get(cookie)
	if !ok || !s.Now().Before(l.AccessExpires) {
		return nil, domain.Fail(domain.Unauthenticated, "SESSION_REQUIRED")
	}
	return l, nil
}
func (s Identity) Guest(key, cookie string) (*Login, error) {
	k := ReplayKey{Scope: "guest", Key: key}
	if l, ok := s.Retries.Get(k); ok {
		if l.Access != cookie {
			return nil, domain.Fail(domain.Conflict, "GUEST_SESSION_ALREADY_ISSUED")
		}
		return s.Session(cookie)
	}
	l := s.issue(&domain.Actor{ID: s.ID(), Kind: "guest"})
	s.Retries.Put(k, l)
	return l, nil
}

type MedicalConsent struct {
	Version  string `json:"version"`
	Accepted bool   `json:"accepted"`
}

func (s Identity) Register(key, email, password string, consent MedicalConsent) (*Login, error) {
	if !consent.Accepted {
		return nil, domain.Fail(domain.Invalid, "VALIDATION_ERROR")
	}
	if consent.Version != PolicyVersion {
		return nil, domain.Fail(domain.Invalid, "CONSENT_VERSION_MISMATCH")
	}
	email = strings.ToLower(email)
	k := ReplayKey{Scope: "register", Key: key}
	account, exists := s.Accounts.Get(email)
	if l, ok := s.Retries.Get(k); ok {
		if !exists || account.Actor.ID != l.Actor.ID || !s.Passwords.Matches(account.Hash, password) {
			return nil, domain.Fail(domain.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
		return s.Session(l.Access)
	}
	if exists || email == moderatorEmail {
		return nil, domain.Fail(domain.Conflict, "ACCOUNT_ALREADY_EXISTS")
	}
	hash, err := s.Passwords.Hash(password)
	if err != nil {
		return nil, err
	}
	a := &domain.Actor{ID: s.ID(), Kind: "member", Consent: true}
	s.Accounts.Put(email, Account{a, hash})
	l := s.issue(a)
	s.Retries.Put(k, l)
	return l, nil
}
func (s Identity) SignIn(email, password string) (*Login, error) {
	email = strings.ToLower(email)
	if email == moderatorEmail && s.ModeratorPassword != "" && subtle.ConstantTimeCompare([]byte(password), []byte(s.ModeratorPassword)) == 1 {
		a, ok := s.Accounts.Get(email)
		if !ok {
			a.Actor = &domain.Actor{ID: s.ID(), Kind: "staff"}
			s.Accounts.Put(email, a)
		}
		return s.issue(a.Actor), nil
	}
	a, ok := s.Accounts.Get(email)
	if !ok || !s.Passwords.Matches(a.Hash, password) {
		return nil, domain.Fail(domain.Unauthenticated, "INVALID_CREDENTIALS")
	}
	return s.issue(a.Actor), nil
}
func (s Identity) Revoke(l *Login) { s.Access.Delete(l.Access); s.Refreshes.Delete(l.Refresh) }
func (s Identity) Rotate(cookie, _ string) (*Login, error) {
	l, ok := s.Refreshes.Get(cookie)
	if !ok || !s.Now().Before(l.Expires) {
		return nil, domain.Fail(domain.Unauthenticated, "SESSION_REQUIRED")
	}
	if cookie != l.Refresh {
		s.Revoke(l)
		return nil, domain.Fail(domain.Unauthenticated, "SESSION_REQUIRED")
	}
	s.Access.Delete(l.Access)
	l.Access, l.Refresh = s.Token(), s.Token()
	l.AccessExpires = s.Now().Add(168 * time.Hour)
	if l.Expires.Before(l.AccessExpires) {
		l.AccessExpires = l.Expires
	}
	s.Access.Put(l.Access, l)
	s.Refreshes.Put(l.Refresh, l)
	return l, nil
}
