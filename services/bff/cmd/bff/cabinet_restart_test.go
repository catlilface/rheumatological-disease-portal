package main

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"portal/bff/internal/adapters/archive"
	"portal/bff/internal/adapters/httpapi"
	app "portal/bff/internal/application"
	"portal/bff/internal/config"
	"portal/bff/internal/domain"
)

const testSession = "01980000-0000-7000-8000-000000000001"

type testPatient struct{ httpapi.Identity }

func (testPatient) Session(context.Context, string) (*app.Login, error) {
	return &app.Login{Actor: &domain.Actor{ID: "patient", Kind: "member", Consent: true}, SessionID: testSession}, nil
}
func (testPatient) Check(context.Context, *app.Login, string, domain.Resource, string) (time.Time, error) {
	return time.Now().Add(time.Second), nil
}

func TestCabinetReceiptSurvivesBFFRestart(t *testing.T) {
	root, err := config.Root()
	if err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(t.TempDir(), "patient.db")
	key := uuid.NewString()
	body := `{"name":"medicine","dose_text":"test","local_times":["09:00"],"starts_on":"2026-01-01"}`
	var location string
	for boot := 0; boot < 2; boot++ {
		db, err := archive.Open(file)
		if err != nil {
			t.Fatal(err)
		}
		api, err := build(root, config.Settings{Hosts: []string{"localhost"}}, testPatient{}, nil, db)
		if err != nil {
			t.Fatal(err)
		}
		send := func(method, path, body string, status int) *httptest.ResponseRecorder {
			r := httptest.NewRequest(method, "https://localhost"+path, strings.NewReader(body))
			r.Header.Set("Origin", "https://localhost")
			r.Header.Set("X-Portal-Request", "1")
			r.Header.Set("Idempotency-Key", key)
			r.Header.Set("X-Portal-Session", testSession)
			w := httptest.NewRecorder()
			api.ServeHTTP(w, r)
			if w.Code != status {
				t.Fatalf("%s %s: %d, want %d", method, path, w.Code, status)
			}
			return w
		}
		const meds = "/api/v1/me/medications"
		if boot == 1 {
			send("GET", location, "", 200)
		}
		receipt := send("POST", meds, body, 202).Header().Get("Location")
		if boot == 1 && receipt != location {
			t.Fatal("retry issued a new operation")
		}
		location = receipt
		send("POST", meds, strings.Replace(body, "medicine", "different", 1), 409)
		var page domain.Page[domain.Medication]
		if err := json.Unmarshal(send("GET", meds, "", 200).Body.Bytes(), &page); err != nil || page.Total != 1 {
			t.Fatalf("medications: %d, err %v", page.Total, err)
		}
		if err := db.Close(); err != nil {
			t.Fatal(err)
		}
	}
}
