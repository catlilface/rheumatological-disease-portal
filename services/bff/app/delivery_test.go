package app

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"portal/bff/cmd/config"
)

func TestDeliveryHTTPRecovery(t *testing.T) {
	dsn, brokers := os.Getenv("TEST_DELIVERY_DSN"), os.Getenv("TEST_KAFKA_BROKERS")
	if dsn == "" || brokers == "" {
		t.Skip("run make test-bff-delivery")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	root, err := config.Root()
	if err != nil {
		t.Fatal(err)
	}
	cfg := config.Defaults()
	prefix := "http-delivery-" + uuid.NewString()
	cfg.Delivery = config.Delivery{
		Enabled: true, DSN: dsn, Brokers: brokers, TopicPrefix: prefix, Group: prefix,
		MaxAttempts: 3, RetryDelay: time.Millisecond, PollInterval: 10 * time.Millisecond, PublishTimeout: 5 * time.Second,
	}
	start := func() (http.Handler, func()) {
		t.Helper()
		runtime, stop, err := startDelivery(ctx, cfg.Delivery)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(stop)
		api, err := build(root, cfg, dependencies{auth: testPatient{}, delivery: runtime})
		if err != nil {
			t.Fatal(err)
		}
		return api, stop
	}
	api, stop := start()
	id, op := uuid.NewString(), uuid.NewString()
	input, err := json.Marshal(map[string]any{
		"entity_id": id, "operation_id": op, "message_id": uuid.NewString(),
		"version": 1, "action": "increment", "delta": 3,
	})
	if err != nil {
		t.Fatal(err)
	}
	request := func(method, path string, body []byte) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(method, "http://localhost/_demo/delivery"+path, strings.NewReader(string(body)))
		req.Header.Set("Origin", "http://localhost")
		req.Header.Set("X-Portal-Request", "1")
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		api.ServeHTTP(rec, req)
		return rec
	}
	assertStatus := func(rec *httptest.ResponseRecorder, want int) {
		t.Helper()
		if rec.Code != want {
			t.Fatalf("got %d, want %d: %s", rec.Code, want, rec.Body)
		}
	}
	assertStatus(request(http.MethodPost, "/commands", input), http.StatusAccepted)
	operation := "/operations/" + op
	assertStatus(request(http.MethodGet, operation, nil), http.StatusNotFound)
	counter := "/counters/" + id
	outbox := request(http.MethodGet, counter+"/outbox", nil)
	assertStatus(outbox, http.StatusOK)
	var rows []struct {
		PublishedAt *time.Time `json:"published_at"`
	}
	if err := json.Unmarshal(outbox.Body.Bytes(), &rows); err != nil || len(rows) != 1 || rows[0].PublishedAt != nil {
		t.Fatalf("expected a single pending message, got %s (%v)", outbox.Body, err)
	}

	stop()
	cfg.Delivery.Publish = true
	api, _ = start()
	for ctx.Err() == nil {
		state := request(http.MethodGet, counter, nil)
		assertStatus(state, http.StatusOK)
		if strings.TrimSpace(state.Body.String()) == `{"value":3,"projected":3}` {
			break
		}
		pause(ctx, cfg.Delivery.PollInterval)
	}
	if ctx.Err() != nil {
		t.Fatal("counter projection did not recover")
	}
	assertStatus(request(http.MethodPost, "/commands", input), http.StatusAccepted)
	result := request(http.MethodGet, operation, nil)
	assertStatus(result, http.StatusOK)
	var outcome struct {
		Status string
		Result struct{ Value int }
	}
	if err := json.Unmarshal(result.Body.Bytes(), &outcome); err != nil || outcome.Status != "succeeded" || outcome.Result.Value != 3 {
		t.Fatalf("unexpected outcome %s (%v)", result.Body, err)
	}
}
