package delivery_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/twmb/franz-go/pkg/kgo"

	"portal/bff/internal/repo"
	"portal/bff/internal/service"
	"portal/bff/pkg/delivery"
)

type failedCommit struct{ *kgo.Client }

func (failedCommit) CommitRecords(context.Context, ...*kgo.Record) error {
	return errors.New("simulated failure before offset commit")
}

func require(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func TestDeliveryRecovery(t *testing.T) {
	dsn, brokers := os.Getenv("TEST_DELIVERY_DSN"), os.Getenv("TEST_KAFKA_BROKERS")
	if dsn == "" || brokers == "" {
		t.Skip("run make test-bff-delivery")
	}
	ctx, stop := context.WithTimeout(context.Background(), 90*time.Second)
	defer stop()
	db, err := sql.Open("pgx", dsn)
	require(t, err)
	defer db.Close()
	require(t, db.PingContext(ctx))

	prefix := "go-delivery-" + uuid.NewString()
	options := delivery.Options{DeadLetterTopic: prefix + ".dead", MaxAttempts: 3, PublishTimeout: 10 * time.Second}
	newProducer := func() *kgo.Client {
		client, err := kgo.NewClient(kgo.SeedBrokers(brokers), kgo.AllowAutoTopicCreation())
		require(t, err)
		t.Cleanup(client.Close)
		return client
	}
	producer := newProducer()
	transport, err := delivery.New(db, producer, options)
	require(t, err)
	repository := repo.DeliveryCounters{DB: db}
	demo := service.DeliveryDemo{Transport: transport, Counters: repository, CommandTopic: prefix + ".commands", EventTopic: prefix + ".events"}
	newConsumer := func(topic, group string) *kgo.Client {
		client, err := kgo.NewClient(kgo.SeedBrokers(brokers), kgo.AllowAutoTopicCreation(),
			kgo.ConsumerGroup(group), kgo.ConsumeTopics(topic), kgo.DisableAutoCommit(), kgo.BlockRebalanceOnPoll())
		require(t, err)
		t.Cleanup(client.CloseAllowingRebalance)
		return client
	}
	commandGroup := prefix + ".command"
	commands := newConsumer(demo.CommandTopic, commandGroup)
	events := newConsumer(demo.EventTopic, prefix+".event")
	drain := func() {
		t.Helper()
		for {
			ok, err := transport.PublishOne(ctx)
			require(t, err)
			if !ok {
				return
			}
		}
	}
	assertOutcome := func(id uuid.UUID, key, want string) {
		t.Helper()
		value, err := transport.Operation(ctx, id)
		require(t, err)
		var body map[string]json.RawMessage
		require(t, json.Unmarshal(value, &body))
		if string(body[key]) != `"`+want+`"` {
			t.Fatalf("operation %s: got %s, want %s=%s", id, value, key, want)
		}
	}
	assertCounter := func(id uuid.UUID, value int64, projected bool) {
		t.Helper()
		state, err := repository.Counter(ctx, id)
		require(t, err)
		if state.Value == nil || *state.Value != value ||
			projected && (state.Projected == nil || *state.Projected != value) ||
			!projected && state.Projected != nil {
			t.Fatalf("unexpected counter or projection for %s: %+v", id, state)
		}
	}
	command := func(id uuid.UUID, version int64, action string) service.CounterCommand {
		return service.CounterCommand{MessageID: uuid.New(), OperationID: uuid.New(), EntityID: id, Version: version,
			CounterChange: service.CounterChange{Action: action, Delta: 3}}
	}
	id := uuid.New()
	first := command(id, 1, "increment")
	require(t, demo.Submit(ctx, first))
	require(t, demo.Submit(ctx, first))
	changed := first
	changed.Delta++
	if err := demo.Submit(ctx, changed); !errors.Is(err, delivery.ErrConflict) {
		t.Fatalf("expected conflict, got %v", err)
	}
	drain()
	err = transport.ConsumeOne(ctx, failedCommit{commands}, demo.ApplyCommand)
	if err == nil || err.Error() != "simulated failure before offset commit" {
		t.Fatalf("expected offset commit failure, got %v", err)
	}
	commands.CloseAllowingRebalance()
	assertCounter(id, 3, false)
	assertOutcome(first.OperationID, "status", "succeeded")

	producer.Close()
	transport, err = delivery.New(db, newProducer(), options)
	require(t, err)
	demo.Transport = transport
	commands = newConsumer(demo.CommandTopic, commandGroup)
	require(t, transport.ConsumeOne(ctx, commands, func(context.Context, *sql.Tx, delivery.Message) (json.RawMessage, error) {
		t.Fatal("redelivery repeated the effect")
		return nil, nil
	}))
	drain()
	require(t, transport.ConsumeOne(ctx, events, demo.ApplyEvent))
	assertCounter(id, 3, true)

	sameOperation := first
	sameOperation.MessageID = uuid.New()
	require(t, demo.Submit(ctx, sameOperation))
	drain()
	require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))
	changed.MessageID = uuid.New()
	require(t, demo.Submit(ctx, changed))
	drain()
	require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))
	assertOutcome(first.OperationID, "status", "succeeded")

	for _, scenario := range []struct {
		action, code string
		version      int64
		attempts     int
	}{
		{"increment", "version_gap", 3, 1},
		{"increment", "stale_version", 1, 1},
		{"retry", "handler_failed", 2, options.MaxAttempts},
		{"invalid_outcome", "handler_failed", 2, options.MaxAttempts},
		{"reject", "rejected", 2, 1},
	} {
		input := command(id, scenario.version, scenario.action)
		require(t, demo.Submit(ctx, input))
		drain()
		require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))
		assertOutcome(input.OperationID, "error", scenario.code)
		var attempts int
		require(t, db.QueryRowContext(ctx, "SELECT attempts FROM public.kafka_operations WHERE id=$1", input.OperationID).Scan(&attempts))
		if attempts != scenario.attempts {
			t.Fatalf("%s attempts: got %d, want %d", scenario.action, attempts, scenario.attempts)
		}
		assertCounter(id, 3, true)
	}
	var eventCount int
	require(t, db.QueryRowContext(ctx, "SELECT count(*) FROM public.kafka_outbox WHERE topic=$1", demo.EventTopic).Scan(&eventCount))
	if eventCount != 1 {
		t.Fatalf("got %d events after rejected transactions, want 1", eventCount)
	}
	require(t, newProducer().ProduceSync(ctx, &kgo.Record{
		Topic: demo.CommandTopic, Value: []byte("{}"),
		Headers: []kgo.RecordHeader{{Key: delivery.Header, Value: []byte{0xff}}},
	}).FirstErr())
	require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))

	oversized := command(id, 2, "oversized_event")
	require(t, demo.Submit(ctx, oversized))
	drain()
	require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))
	drain()
	rows, err := repository.Outbox(ctx, service.CounterKey(id))
	require(t, err)
	if !strings.Contains(string(rows), `"publish_error": 10`) {
		t.Fatalf("oversized event was not quarantined: %s", rows)
	}
	otherID := uuid.New()
	require(t, demo.Submit(ctx, command(otherID, 1, "increment")))
	drain()
	require(t, transport.ConsumeOne(ctx, commands, demo.ApplyCommand))
	drain()
	require(t, transport.ConsumeOne(ctx, events, demo.ApplyEvent))
	assertCounter(otherID, 3, true)

	dead := newConsumer(options.DeadLetterTopic, prefix+".dead")
	want := map[string]int{"idempotency_conflict": 1, "version_gap": 1, "stale_version": 1, "handler_failed": 2, "rejected": 1, "invalid_message": 1}
	for len(want) > 0 {
		fetch := dead.PollRecords(ctx, 1)
		require(t, fetch.Err())
		iter := fetch.RecordIter()
		if iter.Done() {
			t.Fatal("missing dead letter")
		}
		record := iter.Next()
		var body struct{ Code string }
		require(t, json.Unmarshal(record.Value, &body))
		if want[body.Code] == 0 {
			t.Fatalf("unexpected dead letter %q", body.Code)
		}
		want[body.Code]--
		if want[body.Code] == 0 {
			delete(want, body.Code)
		}
		dead.AllowRebalance()
	}
}
