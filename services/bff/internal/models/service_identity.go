package models

import "time"

type Login struct {
	Actor                  *Actor
	Access, Refresh        string
	Expires, AccessExpires time.Time
	SessionID              string
	Roles                  []string
}

type Account struct {
	Actor *Actor
	Hash  []byte
}

type ReplayKey struct{ Scope, Key, Credential string }

type MedicalConsent struct {
	Version  string `json:"version"`
	Accepted bool   `json:"accepted"`
}

type Principal struct {
	SessionID        string    `json:"session_id"`
	Kind             string    `json:"kind"`
	Roles            []string  `json:"roles"`
	SessionExpiresAt time.Time `json:"session_expires_at"`
}
