package main

import (
	"net/http/httptest"
	"strings"
	"testing"

	"portal/bff/internal/config"
)

func TestScalarReference(t *testing.T) {
	root, err := config.Root()
	if err != nil {
		t.Fatal(err)
	}
	api, err := build(root, config.Settings{Hosts: []string{"localhost"}})
	if err != nil {
		t.Fatal(err)
	}
	for path, marker := range map[string]string{
		"/scalar":                     "/scalar/bff-v1.openapi.yaml",
		"/scalar/bff-v1.openapi.yaml": "schemas.yaml#/$defs/Accepted",
		"/scalar/schemas.yaml":        "$defs:",
	} {
		w := httptest.NewRecorder()
		api.ServeHTTP(w, httptest.NewRequest("GET", "https://localhost"+path, nil))
		if w.Code != 200 || !strings.Contains(w.Body.String(), marker) {
			t.Errorf("GET %s: status %d, expected %q", path, w.Code, marker)
		}
	}
}
