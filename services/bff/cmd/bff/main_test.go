package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"

	"portal/bff/internal/config"
)

func TestConcurrentIntentAppliesOnce(t *testing.T) {
	root, err := config.Root()
	if err != nil {
		t.Fatal(err)
	}
	api, err := build(root, config.Settings{Hosts: []string{"localhost"}})
	if err != nil {
		t.Fatal(err)
	}
	send := func(path, key, body string, cookie *http.Cookie) *httptest.ResponseRecorder {
		r := httptest.NewRequest("POST", "https://localhost/api/v1"+path, strings.NewReader(body))
		r.Header.Set("Origin", "https://localhost")
		r.Header.Set("X-Portal-Request", "1")
		r.Header.Set("Idempotency-Key", key)
		if cookie != nil {
			r.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		api.ServeHTTP(w, r)
		return w
	}
	guestKey := uuid.NewString()
	guest := send("/auth/guest-sessions", guestKey, "", nil)
	if guest.Code != 201 {
		t.Fatal(guest.Body.String())
	}
	cookies := guest.Result().Cookies()
	if len(cookies) != 2 || !cookies[0].HttpOnly || !cookies[0].Secure || cookies[1].SameSite != http.SameSiteStrictMode || cookies[1].Path != "/api/v1/auth/session" {
		t.Fatal("missing session cookie protections")
	}
	if send("/auth/guest-sessions", guestKey, "", nil).Code != 409 {
		t.Fatal("guest replay key acted as a credential")
	}
	const start = `{"survey_id":"rheuma_screening_v1","disclaimer_version":"demo-v1","weights_version":"draft-v1","disclaimer_accepted":true}`
	key := uuid.NewString()
	locations := make(chan string, 16)
	var wg sync.WaitGroup
	for range cap(locations) {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w := send("/screenings", key, start, cookies[0])
			if w.Code != 202 {
				t.Error(w.Code)
				return
			}
			locations <- w.Header().Get("Location")
		}()
	}
	wg.Wait()
	close(locations)
	var location string
	for value := range locations {
		if location != "" && value != location {
			t.Fatal("duplicate operation")
		}
		location = value
	}
	if !strings.HasPrefix(location, "/api/v1/operations/screening/") {
		t.Fatalf("unexpected status URL: %q", location)
	}
	get := func(cookie *http.Cookie) *httptest.ResponseRecorder {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "https://localhost"+location, nil)
		r.AddCookie(cookie)
		api.ServeHTTP(w, r)
		return w
	}
	op := get(cookies[0])
	var result struct {
		State     string
		Resources []struct{ Version int }
	}
	if err := json.Unmarshal(op.Body.Bytes(), &result); err != nil || result.State != "succeeded" || len(result.Resources) != 1 || result.Resources[0].Version != 1 {
		t.Fatal(op.Body.String())
	}
	other := send("/auth/guest-sessions", uuid.NewString(), "", nil)
	if get(other.Result().Cookies()[0]).Code != 404 {
		t.Fatal("disclosed another owner's operation")
	}
}
