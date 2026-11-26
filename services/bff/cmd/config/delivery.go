package config

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Delivery struct {
	Enabled, Publish                         bool
	DSN, Brokers, TopicPrefix, Group         string
	MaxAttempts                              int
	RetryDelay, PollInterval, PublishTimeout time.Duration
}

func deliverySettings(source map[string]string) (Delivery, error) {
	cfg := Delivery{
		Publish: true, Brokers: "kafka:19092", TopicPrefix: "dev.bff.delivery.v1",
		Group: "bff-delivery-demo", MaxAttempts: 3, RetryDelay: 200 * time.Millisecond,
		PollInterval: 250 * time.Millisecond, PublishTimeout: 10 * time.Second,
	}
	for key, dest := range map[string]*bool{
		"BFF_DELIVERY_ENABLED": &cfg.Enabled, "BFF_DELIVERY_PUBLISH": &cfg.Publish,
	} {
		if raw, ok := source[key]; ok {
			parsed, err := strconv.ParseBool(raw)
			if err != nil {
				return cfg, fmt.Errorf("invalid %s", key)
			}
			*dest = parsed
		}
	}
	if !cfg.Enabled {
		return cfg, nil
	}
	for key, dest := range map[string]*string{
		"BFF_DELIVERY_BROKERS": &cfg.Brokers, "BFF_DELIVERY_TOPIC_PREFIX": &cfg.TopicPrefix,
		"BFF_DELIVERY_GROUP": &cfg.Group, "BFF_DELIVERY_DSN": &cfg.DSN,
	} {
		if raw, ok := source[key]; ok {
			*dest = raw
		}
	}
	for key, dest := range map[string]*time.Duration{
		"BFF_DELIVERY_RETRY_DELAY":     &cfg.RetryDelay,
		"BFF_DELIVERY_POLL_INTERVAL":   &cfg.PollInterval,
		"BFF_DELIVERY_PUBLISH_TIMEOUT": &cfg.PublishTimeout,
	} {
		if raw, ok := source[key]; ok {
			value, err := time.ParseDuration(raw)
			if err != nil || value <= 0 {
				return cfg, fmt.Errorf("invalid %s: expected a positive duration", key)
			}
			*dest = value
		}
	}
	if raw, ok := source["BFF_DELIVERY_MAX_ATTEMPTS"]; ok {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 {
			return cfg, errors.New("invalid BFF_DELIVERY_MAX_ATTEMPTS: expected a positive integer")
		}
		cfg.MaxAttempts = value
	}
	if cfg.Brokers == "" || cfg.TopicPrefix == "" || cfg.Group == "" {
		return cfg, errors.New("delivery brokers, topic prefix and group are required")
	}
	if cfg.DSN == "" {
		file := source["BFF_DELIVERY_PASSWORD_FILE"]
		if file == "" {
			file = "/run/secrets/db-password"
		}
		password, err := os.ReadFile(file)
		if err != nil || strings.TrimSpace(string(password)) == "" {
			return cfg, errors.New("delivery database password is unavailable")
		}
		dsn := url.URL{
			Scheme: "postgres", Host: "postgres:5432", Path: "/mis_bff",
			User:     url.UserPassword("mis_bff_app", strings.TrimSpace(string(password))),
			RawQuery: "sslmode=disable",
		}
		cfg.DSN = dsn.String()
	}
	return cfg, nil
}
