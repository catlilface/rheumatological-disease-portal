// Package domain contains the rules of the synthetic portal. It has no transport or storage dependencies.
package domain

import (
	"strings"
	"time"
)

type Kind int

const (
	Invalid Kind = iota
	Unauthenticated
	Forbidden
	Missing
	Conflict
	Gone
)

type Problem struct {
	Kind    Kind   `json:"-"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

func (p *Problem) Error() string { return p.Code }
func Fail(k Kind, code string) *Problem {
	return &Problem{k, code, strings.ToLower(strings.ReplaceAll(code, "_", " "))}
}
func NotFound() error { return Fail(Missing, "NOT_FOUND") }

type Actor struct {
	ID, Kind string
	Consent  bool
}

func (a *Actor) RequireRegistered() error {
	if a.Kind == "guest" {
		return Fail(Forbidden, "REGISTRATION_REQUIRED")
	}
	return nil
}
func (a *Actor) RequireModerator() error {
	if err := a.RequireRegistered(); err != nil {
		return err
	}
	if a.Kind != "staff" {
		return Fail(Forbidden, "MODERATOR_REQUIRED")
	}
	return nil
}
func (a *Actor) WithdrawConsent() error {
	if a.Kind != "member" {
		return Fail(Forbidden, "PATIENT_REQUIRED")
	}
	a.Consent = false
	return nil
}
func (a *Actor) RequirePatient() error {
	if a.Kind != "member" || !a.Consent {
		return Fail(Forbidden, "CONSENT_REQUIRED")
	}
	return nil
}

type Resource struct {
	Type    string `json:"resource_type"`
	ID      string `json:"resource_id"`
	Version int    `json:"version,omitempty"`
}

func Ref(kind, id string, v ...int) Resource {
	r := Resource{Type: kind, ID: id}
	if len(v) > 0 {
		r.Version = v[0]
	}
	return r
}

type Operation struct {
	ID        string     `json:"operation_id"`
	State     string     `json:"state"`
	Resources []Resource `json:"resources"`
	UpdatedAt time.Time  `json:"updated_at"`
	Error     *Problem   `json:"error,omitempty"`
}
type Window struct{ Limit, Offset int }
type Page[T any] struct {
	Items  []T `json:"items"`
	Total  int `json:"total"`
	Limit  int `json:"limit"`
	Offset int `json:"offset"`
}

func Paginate[T any](items []T, w Window) Page[T] {
	i := min(w.Offset, len(items))
	n := min(w.Limit, len(items)-i)
	return Page[T]{append([]T{}, items[i:i+n]...), len(items), w.Limit, w.Offset}
}
