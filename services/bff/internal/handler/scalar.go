package handler

import (
	"io"
	"io/fs"
	"net/http"
	"net/url"

	scalar "github.com/bdpiprava/scalar-go"

	"portal/bff/cmd/config"
)

const (
	scalarPath = "/scalar"
	scalarCDN  = "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.83.0"
)

func (a *API) reference(files fs.FS) {
	// Keep the external $refs adjacent to the document without serving the whole directory.
	for _, name := range []string{config.OpenAPIFile, config.SchemaFile} {
		a.mux.HandleFunc(http.MethodGet+" "+scalarPath+"/"+name, func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/yaml")
			http.ServeFileFS(w, r, files, name)
		})
	}
	a.mux.HandleFunc(http.MethodGet+" "+scalarPath, func(w http.ResponseWriter, r *http.Request) {
		scheme := "http"
		if r.TLS != nil {
			scheme = "https"
		}
		source := url.URL{Scheme: scheme, Host: r.Host, Path: scalarPath + "/" + config.OpenAPIFile}
		page, err := scalar.NewV2(
			scalar.WithSpecURL(source.String()),
			scalar.WithCDN(scalarCDN),
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
