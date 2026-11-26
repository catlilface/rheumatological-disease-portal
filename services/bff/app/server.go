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
)

func Run(args []string) error {
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
	var delivery *deliveryRuntime
	if cfg.Delivery.Enabled {
		var stop func()
		delivery, stop, err = startDelivery(ctx, cfg.Delivery)
		if err != nil {
			return err
		}
		defer stop()
	}
	handler, err := build(root, cfg, delivery)
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
