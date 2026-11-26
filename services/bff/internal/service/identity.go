package service

import (
	"crypto/subtle"
	"strings"
	"time"

	"portal/bff/internal/models"
)

const PolicyVersion = "demo-medical-v1"

type Login = models.Login

type Account = models.Account

type Passwords interface {
	Hash(string) ([]byte, error)
	Matches([]byte, string) bool
}

type ReplayKey = models.ReplayKey
type Identity struct {
	Runtime
	Access, Refreshes Store[string, *Login]
	Accounts          Store[string, Account]
	Retries           Store[ReplayKey, *Login]
	Passwords         Passwords
	ModeratorPassword string
	ModeratorEmail    string
	SessionTTL        time.Duration
}

func (s Identity) issue(a *models.Actor) *Login {
	l := &Login{
		Actor:   a,
		Access:  s.Token(),
		Refresh: s.Token(),
		Expires: s.Now().Add(s.SessionTTL),
	}
	s.Access.Put(l.Access, l)
	s.Refreshes.Put(l.Refresh, l)
	return l
}

func (s Identity) Session(cookie string) (*Login, error) {
	l, ok := s.Access.Get(cookie)
	if !ok || !s.Now().Before(l.Expires) {
		return nil, models.Fail(models.Unauthenticated, "SESSION_REQUIRED")
	}
	return l, nil
}

func (s Identity) Guest(key, cookie string) (*Login, error) {
	k := ReplayKey{Scope: "guest", Key: key}
	if l, ok := s.Retries.Get(k); ok {
		if l.Access != cookie {
			return nil, models.Fail(models.Conflict, "GUEST_SESSION_ALREADY_ISSUED")
		}
		return s.Session(cookie)
	}
	l := s.issue(&models.Actor{ID: s.ID(), Kind: models.GuestActor})
	s.Retries.Put(k, l)
	return l, nil
}

type MedicalConsent = models.MedicalConsent

func (s Identity) Register(key, email, password string, consent MedicalConsent) (*Login, error) {
	if !consent.Accepted {
		return nil, models.Fail(models.Invalid, "VALIDATION_ERROR")
	}
	if consent.Version != PolicyVersion {
		return nil, models.Fail(models.Invalid, "CONSENT_VERSION_MISMATCH")
	}
	email = strings.ToLower(email)
	k := ReplayKey{Scope: "register", Key: key}
	account, exists := s.Accounts.Get(email)
	if l, ok := s.Retries.Get(k); ok {
		if !exists || account.Actor.ID != l.Actor.ID || !s.Passwords.Matches(account.Hash, password) {
			return nil, models.Fail(models.Conflict, "IDEMPOTENCY_KEY_REUSED")
		}
		return s.Session(l.Access)
	}
	if exists || email == s.ModeratorEmail {
		return nil, models.Fail(models.Conflict, "ACCOUNT_ALREADY_EXISTS")
	}
	hash, err := s.Passwords.Hash(password)
	if err != nil {
		return nil, err
	}
	a := &models.Actor{ID: s.ID(), Kind: models.MemberActor, Consent: true}
	s.Accounts.Put(email, Account{a, hash})
	l := s.issue(a)
	s.Retries.Put(k, l)
	return l, nil
}

func (s Identity) SignIn(email, password string) (*Login, error) {
	email = strings.ToLower(email)
	if email == s.ModeratorEmail && s.validModeratorPassword(password) {
		a, ok := s.Accounts.Get(email)
		if !ok {
			a.Actor = &models.Actor{ID: s.ID(), Kind: models.StaffActor}
			s.Accounts.Put(email, a)
		}
		return s.issue(a.Actor), nil
	}
	a, ok := s.Accounts.Get(email)
	if !ok || !s.Passwords.Matches(a.Hash, password) {
		return nil, models.Fail(models.Unauthenticated, "INVALID_CREDENTIALS")
	}
	return s.issue(a.Actor), nil
}

func (s Identity) validModeratorPassword(password string) bool {
	return s.ModeratorPassword != "" &&
		subtle.ConstantTimeCompare([]byte(password), []byte(s.ModeratorPassword)) == 1
}

func (s Identity) Revoke(login *Login) {
	s.Access.Delete(login.Access)
	s.Refreshes.Delete(login.Refresh)
}

func (s Identity) Rotate(cookie, key string) (*Login, error) {
	k := ReplayKey{"refresh", key, cookie}
	if l, ok := s.Retries.Get(k); ok {
		return s.Session(l.Access)
	}
	old, ok := s.Refreshes.Get(cookie)
	if !ok || !s.Now().Before(old.Expires) {
		return nil, models.Fail(models.Unauthenticated, "SESSION_REQUIRED")
	}
	s.Revoke(old)
	l := s.issue(old.Actor)
	s.Retries.Put(k, l)
	s.Retries.Put(ReplayKey{"refresh", key, l.Refresh}, l)
	return l, nil
}
