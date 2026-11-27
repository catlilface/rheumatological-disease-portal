package main

import (
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"

	"portal/bff/app"
)

func main() {
	err := app.Run(os.Args[1:])
	if err != nil && !errors.Is(err, flag.ErrHelp) && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("BFF failed", "error", err)
		os.Exit(1)
	}
}
