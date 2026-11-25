package httpapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"portal/bff/internal/config"
)

func TestBrowserBoundary(t *testing.T) {
	cfg := config.Settings{Hosts: []string{"api.test"}, CORS: config.CORS{Origins: []string{"https://web.test"}, Methods: []string{"GET", "POST"}, Headers: []string{"Authorization"}, Credentials: true, Expose: []string{"X-Request-ID"}, MaxAge: 120}}
	a := &API{cfg: cfg, mux: http.NewServeMux()}
	a.mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })
	for _, tc := range []struct {
		name, host, origin, method, reqMethod, header string
		status                                        int
	}{{"same host", "api.test", "", "GET", "", "", 200}, {"host with port", "api.test:8000", "", "GET", "", "", 200}, {"untrusted host", "attacker.test", "https://web.test", "OPTIONS", "GET", "", 400}, {"allowed origin", "api.test", "https://web.test", "GET", "", "", 200}, {"untrusted origin", "api.test", "https://other.test", "GET", "", "", 200}, {"allowed preflight", "api.test", "https://web.test", "OPTIONS", "POST", "Authorization", 200}, {"denied method", "api.test", "https://web.test", "OPTIONS", "PUT", "", 400}, {"denied header", "api.test", "https://web.test", "OPTIONS", "GET", "X-Other", 400}, {"denied origin", "api.test", "https://other.test", "OPTIONS", "GET", "", 400}} {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest(tc.method, "http://"+tc.host+"/health", nil)
			r.Header.Set("Origin", tc.origin)
			r.Header.Set("Access-Control-Request-Method", tc.reqMethod)
			r.Header.Set("Access-Control-Request-Headers", tc.header)
			w := httptest.NewRecorder()
			a.ServeHTTP(w, r)
			if w.Code != tc.status {
				t.Fatalf("got %d", w.Code)
			}
			h := w.Header()
			if tc.origin != "https://web.test" || tc.host == "attacker.test" {
				if h.Get("Access-Control-Allow-Origin") != "" {
					t.Fatal("granted untrusted origin")
				}
			} else if h.Get("Access-Control-Allow-Origin") != tc.origin || h.Get("Access-Control-Allow-Credentials") != "true" || h.Get("Access-Control-Expose-Headers") != "X-Request-ID" {
				t.Fatal(h)
			}
			if tc.name == "allowed preflight" && (h.Get("Access-Control-Max-Age") != "120" || !strings.Contains(h.Get("Access-Control-Allow-Headers"), "Authorization")) {
				t.Fatal(h)
			}
		})
	}
}
