package app

import (
	"context"
	"errors"
	"flag"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"portal/bff/cmd/config"
	"portal/bff/internal/repo/archive"
	"portal/bff/internal/repo/iam"
)

func Run(args []string) error {
	return run(args, production)
}

func production(config.Settings) (dependencies, error) {
	auth, err := iam.Dial("iam:50051", "/run/iam-tls")
	if err != nil {
		return dependencies{}, err
	}
	path := os.Getenv("PORTAL_ARCHIVE_PATH")
	if path == "" {
		path = "/var/lib/portal/patients.db"
	}
	db, err := archive.Open(path)
	return dependencies{auth: auth, archive: db}, err
}

func run(args []string, open func(config.Settings) (dependencies, error)) error {
	flags := flag.NewFlagSet("bff", flag.ContinueOnError)
	addr := flags.String("addr", "", "listen address (defaults to BFF_HTTP_ADDR)")
	cert := flags.String("tls-cert", "", "PEM certificate for direct HTTPS (otherwise terminate TLS at ingress)")
	key := flags.String("tls-key", "", "PEM private key for direct HTTPS")
	if err := flags.Parse(args); err != nil {
		return err
	}
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
	if *addr == "" {
		*addr = cfg.HTTP.Address
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	deps, err := open(cfg)
	if err != nil {
		return err
	}
	if deps.archive != nil {
		defer deps.archive.Close()
	}
	if cfg.Delivery.Enabled {
		var stop func()
		deps.delivery, stop, err = startDelivery(ctx, cfg.Delivery)
		if err != nil {
			return err
		}
		defer stop()
	}
	handler, err := build(root, cfg, deps)
	if err != nil {
		return err
	}
	server := &http.Server{
		Handler:           handler,
		ReadHeaderTimeout: cfg.HTTP.ReadHeaderTimeout,
		ReadTimeout:       cfg.HTTP.ReadTimeout,
		WriteTimeout:      cfg.HTTP.WriteTimeout,
		IdleTimeout:       cfg.HTTP.IdleTimeout,
	}
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		return err
	}
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
		shutdown, stop := context.WithTimeout(context.Background(), cfg.HTTP.ShutdownTimeout)
		defer stop()
		return server.Shutdown(shutdown)
	}
}
