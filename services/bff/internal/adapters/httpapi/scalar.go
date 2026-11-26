package httpapi

import (
	"io"
	"io/fs"
	"net/http"
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
		const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>BFF API Reference</title></head>
<body>
<div id="app"></div>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.83.0"></script>
<script>Scalar.createApiReference('#app', {url: '/scalar/` + spec + `', showToolbar: 'never'})</script>
</body></html>`
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = io.WriteString(w, page)
	})
}
