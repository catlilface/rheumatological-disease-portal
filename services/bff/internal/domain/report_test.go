package domain

import (
	"testing"
	"time"
)

func TestGrantExpiry(t *testing.T) {
	at := time.Now().UTC()
	g := Grant{Owner: &Actor{Consent: true}, Share: Share{Expires: at}}
	if _, err := g.Active(at.Add(-time.Nanosecond)); err != nil {
		t.Fatal(err)
	}
	if _, err := g.Active(at); err == nil {
		t.Fatal("grant accepted at its expiry")
	}
	g.Owner.Consent = false
	if _, err := g.Active(at.Add(-time.Hour)); err == nil {
		t.Fatal("grant outlived owner's consent")
	}
}
