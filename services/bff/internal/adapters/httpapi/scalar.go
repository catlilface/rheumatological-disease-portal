package httpapi

import (
	"io"
	"io/fs"
	"net/http"
	"net/url"

	scalar "github.com/bdpiprava/scalar-go"
)

func (a *API) reference(files fs.FS) {
	const spec = "bff-v1.openapi.yaml"
	// Keep the external $refs adjacent to the document without serving the whole directory.
	for _, name := range []string{spec, "schemas.yaml"} {
		a.mux.HandleFunc("GET /scalar/"+name, func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/yaml")
			http.ServeFileFS(w, r, files, name)
		})
	}
	a.mux.HandleFunc("GET /scalar", func(w http.ResponseWriter, r *http.Request) {
		scheme := "http"
		if r.TLS != nil {
			scheme = "https"
		}
		source := url.URL{Scheme: scheme, Host: r.Host, Path: "/scalar/" + spec}
		page, err := scalar.NewV2(
			scalar.WithSpecURL(source.String()),
			scalar.WithCDN("https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.83.0"),
			scalar.WithMetaDataOpts(scalar.WithTitle("BFF API Reference")),
		)
		if err != nil {
			http.Error(w, "API reference unavailable", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = io.WriteString(w, page)
	})
}
