package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

type watchedTransaction struct{ active bool }

func (tx *watchedTransaction) Within(f func()) {
	tx.active = true
	defer func() { tx.active = false }()
	f()
}

type checkedIdentity struct {
	Identity
	t  *testing.T
	tx *watchedTransaction
}

func (i checkedIdentity) Session(context.Context, string) (*application.Login, error) {
	if i.tx.active {
		i.t.Error("Authenticate held the store lock")
	}
	return &application.Login{Actor: &domain.Actor{ID: "patient", Kind: "member", Consent: true}}, nil
}
func (i checkedIdentity) Check(_ context.Context, l *application.Login, _ string, r domain.Resource, owner string) (time.Time, error) {
	if i.tx.active {
		i.t.Error("CheckAccess held the store lock")
	}
	if owner != l.Actor.ID || r.ID != owner {
		i.t.Fatal("unbound ownership check")
	}
	return time.Now().Add(time.Second), nil
}

func TestRemoteAuthorizationOutsideStoreTransaction(t *testing.T) {
	tx := &watchedTransaction{}
	a := &API{mux: http.NewServeMux(), pending: contract{"getOnboarding": {pattern: "GET /cabinet"}}, tx: tx, auth: checkedIdentity{t: t, tx: tx}}
	a.on("getOnboarding", member, func(*call) (any, error) {
		if !tx.active {
			t.Error("local dispatch not protected")
		}
		return nil, nil
	})
	w := httptest.NewRecorder()
	a.mux.ServeHTTP(w, httptest.NewRequest("GET", "/cabinet", nil))
	if w.Code != 200 {
		t.Fatalf("unexpected status %d", w.Code)
	}
}
