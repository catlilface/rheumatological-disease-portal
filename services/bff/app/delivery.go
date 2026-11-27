package app

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/twmb/franz-go/pkg/kgo"

	"portal/bff/cmd/config"
	"portal/bff/internal/repo"
	"portal/bff/internal/service"
	"portal/bff/pkg/delivery"
)

type deliveryRuntime struct {
	service.DeliveryDemo
	counters repo.DeliveryCounters
}

func startDelivery(ctx context.Context, cfg config.Delivery) (*deliveryRuntime, func(), error) {
	db, err := sql.Open("pgx", cfg.DSN)
	if err != nil {
		return nil, nil, errors.New("invalid delivery database configuration")
	}
	producer, err := kgo.NewClient(kgo.SeedBrokers(strings.Split(cfg.Brokers, ",")...), kgo.AllowAutoTopicCreation(), kgo.RecordDeliveryTimeout(cfg.PublishTimeout))
	if err != nil {
		db.Close()
		return nil, nil, err
	}
	workerCtx, cancel := context.WithCancel(ctx)
	var workers sync.WaitGroup
	closeRuntime := func() {
		cancel()
		workers.Wait()
		producer.Close()
		db.Close()
	}
	timeout, stop := context.WithTimeout(ctx, cfg.PublishTimeout)
	defer stop()
	var migrated bool
	err = db.QueryRowContext(timeout, "SELECT to_regclass('public.delivery_demo_projection') IS NOT NULL").Scan(&migrated)
	if err != nil || !migrated {
		closeRuntime()
		return nil, nil, errors.New("delivery database is unavailable or migrations are missing")
	}
	transport, err := delivery.New(db, producer, delivery.Options{
		DeadLetterTopic: cfg.DeadLetterTopic(),
		MaxAttempts:     cfg.MaxAttempts, RetryDelay: cfg.RetryDelay, PublishTimeout: cfg.PublishTimeout,
	})
	if err != nil {
		closeRuntime()
		return nil, nil, err
	}
	counters := repo.DeliveryCounters{DB: db}
	demo := service.DeliveryDemo{
		Transport: transport, Counters: counters,
		CommandTopic: cfg.CommandTopic(), EventTopic: cfg.EventTopic(),
	}
	if cfg.Publish {
		workers.Go(func() {
			for workerCtx.Err() == nil {
				handled, err := transport.PublishOne(workerCtx)
				if err != nil && workerCtx.Err() == nil {
					slog.Warn("delivery publisher could not send a message")
				}
				if !handled {
					pause(workerCtx, cfg.PollInterval)
				}
			}
		})
	}
	workers.Go(func() { consume(workerCtx, cfg, demo.CommandTopic, transport, demo.ApplyCommand) })
	workers.Go(func() { consume(workerCtx, cfg, demo.EventTopic, transport, demo.ApplyEvent) })
	return &deliveryRuntime{demo, counters}, closeRuntime, nil
}

func consume(ctx context.Context, cfg config.Delivery, topic string, transport *delivery.Delivery, handler delivery.Handler) {
	for ctx.Err() == nil {
		client, err := kgo.NewClient(
			kgo.SeedBrokers(strings.Split(cfg.Brokers, ",")...), kgo.AllowAutoTopicCreation(),
			kgo.ConsumerGroup(cfg.Group+"."+topic), kgo.ConsumeTopics(topic), kgo.DisableAutoCommit(), kgo.BlockRebalanceOnPoll(),
		)
		if err == nil {
			for ctx.Err() == nil && err == nil {
				err = transport.ConsumeOne(ctx, client, handler)
			}
			client.CloseAllowingRebalance()
		}
		if ctx.Err() == nil {
			slog.Warn("delivery consumer will reconnect", "topic", topic)
			pause(ctx, cfg.PollInterval)
		}
	}
}

func pause(ctx context.Context, delay time.Duration) {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}
