package handler

import (
	"io"
	"io/fs"
	"net/http"

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
	a.mux.HandleFunc(http.MethodGet+" "+scalarPath, func(w http.ResponseWriter, _ *http.Request) {
		const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>BFF API Reference</title></head>
<body>
<div id="app"></div>
<script src="` + scalarCDN + `"></script>
<script>Scalar.createApiReference('#app', {url: '` + scalarPath + "/" + config.OpenAPIFile + `', showToolbar: 'never'})</script>
</body></html>`
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = io.WriteString(w, page)
	})
}
