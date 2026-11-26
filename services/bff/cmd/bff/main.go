package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"flag"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/google/uuid"

	"portal/bff/internal/adapters/fixtures"
	"portal/bff/internal/adapters/httpapi"
	"portal/bff/internal/adapters/iam"
	"portal/bff/internal/adapters/memory"
	app "portal/bff/internal/application"
	"portal/bff/internal/config"
	"portal/bff/internal/domain"
)

// Composition root: no service locators, global settings or adapter imports in the core.
func build(root string, cfg config.Settings, identity httpapi.Identity, demo httpapi.DemoRegistration) (http.Handler, error) {
	catalog, err := fixtures.Load()
	if err != nil {
		return nil, err
	}
	rt := app.Runtime{
		Now:   func() time.Time { return time.Now().UTC() },
		ID:    func() string { return uuid.Must(uuid.NewV7()).String() },
		Token: func() string { var b [32]byte; rand.Read(b[:]); return base64.RawURLEncoding.EncodeToString(b[:]) },
	}
	commands := app.Commands{Runtime: rt,
		Operations: memory.New[app.OperationKey, domain.Operation](), Receipts: memory.New[app.IntentKey, app.Receipt](),
	}
	api, err := httpapi.New(cfg, os.DirFS(filepath.Join(root, "contracts/http")), &memory.Transactions{}, identity, commands, demo)
	if err != nil {
		return nil, err
	}
	content := app.Content{Library: catalog}
	source, err := content.Article("rheumatoid-arthritis")
	if err != nil {
		return nil, err
	}
	s := app.Screening{Runtime: rt, Definition: catalog.Survey,
		ExplanationSource: app.SourceRef{Slug: source.Slug, Version: source.Version},
		Sessions:          memory.New[app.OwnedID, *domain.Session](), Results: memory.New[app.OwnedResult, domain.Result](),
		Explanations: memory.New[app.OwnedResult, app.Explanation](),
	}
	api.Screening(s)
	api.Content(content)
	api.Cabinet(app.Cabinets{Runtime: rt, Records: memory.New[string, *domain.Cabinet]()})
	api.Community(app.NewCommunity(rt))
	api.Reports(app.Reports{Runtime: rt, Results: s,
		Records: memory.New[app.OwnedID, domain.Report](), Shares: memory.New[app.ShareKey, *domain.Grant](),
		Tokens: memory.New[string, *domain.Grant](),
	}, catalog.PDF)
	return api, api.Ready()
}

type identityFactory func(config.Settings) (httpapi.Identity, httpapi.DemoRegistration, error)

func run(factory identityFactory) error {
	addr := flag.String("addr", ":8000", "listen address")
	cert := flag.String("tls-cert", "", "PEM certificate for direct HTTPS (otherwise terminate TLS at ingress)")
	key := flag.String("tls-key", "", "PEM private key for direct HTTPS")
	flag.Parse()
	if (*cert == "") != (*key == "") {
		return errors.New("supply both -tls-cert and -tls-key")
	}
	root, err := config.Root()
	if err != nil {
		return err
	}
	cfg, err := config.Load(root)
	if err != nil {
		return err
	}
	identity, demo, err := factory(cfg)
	if err != nil {
		return err
	}
	handler, err := build(root, cfg, identity, demo)
	if err != nil {
		return err
	}
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second}
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		return err
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	done := make(chan error, 1)
	go func() {
		if *cert != "" {
			done <- server.ServeTLS(ln, *cert, *key)
		} else {
			done <- server.Serve(ln)
		}
	}()
	slog.Info("BFF listening", "address", ln.Addr(), "service", cfg.Name)
	select {
	case err = <-done:
		return err
	case <-ctx.Done():
		shutdown, stop := context.WithTimeout(context.Background(), 10*time.Second)
		defer stop()
		return server.Shutdown(shutdown)
	}
}
func main() {
	if err := run(func(config.Settings) (httpapi.Identity, httpapi.DemoRegistration, error) {
		client, err := iam.Dial("iam:50051", "/run/iam-tls")
		return client, nil, err
	}); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("BFF failed", "error", err)
		os.Exit(1)
	}
}
