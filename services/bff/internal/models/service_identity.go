package models

import "time"

type Login struct {
	Actor           *Actor
	Access, Refresh string
	Expires         time.Time
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
	Kind             string    `json:"kind"`
	Roles            []string  `json:"roles"`
	SessionExpiresAt time.Time `json:"session_expires_at"`
}
