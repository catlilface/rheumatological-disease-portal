package httpapi

import (
	"log/slog"
	"net"
	"net/http"
	"slices"
	"strconv"
	"strings"

	"github.com/google/uuid"

	"portal/bff/internal/config"
)

type recorder struct {
	http.ResponseWriter
	status int
}

func (w *recorder) WriteHeader(status int) { w.status = status; w.ResponseWriter.WriteHeader(status) }
func allowedHost(host string, hosts []string) bool {
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	for _, h := range hosts {
		if h == "*" || h == host || strings.HasPrefix(h, "*.") && strings.HasSuffix(host, h[1:]) {
			return true
		}
	}
	return false
}
func allow(xs []string, s string) bool { return slices.Contains(xs, s) || slices.Contains(xs, "*") }
func cors(w http.ResponseWriter, r *http.Request, c config.CORS) bool {
	o := r.Header.Get("Origin")
	if o == "" {
		return false
	}
	ok := allow(c.Origins, o)
	h := w.Header()
	h.Add("Vary", "Origin")
	if ok {
		if slices.Contains(c.Origins, "*") && r.Header.Get("Cookie") == "" {
			h.Set("Access-Control-Allow-Origin", "*")
		} else {
			h.Set("Access-Control-Allow-Origin", o)
		}
		if c.Credentials {
			h.Set("Access-Control-Allow-Credentials", "true")
		}
		if len(c.Expose) > 0 {
			h.Set("Access-Control-Expose-Headers", strings.Join(c.Expose, ", "))
		}
	}
	method := r.Header.Get("Access-Control-Request-Method")
	if r.Method != "OPTIONS" || method == "" {
		return false
	}
	methods := c.Methods
	if slices.Contains(methods, "*") {
		methods = []string{"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
	}
	ok = ok && slices.Contains(methods, method)
	hs := append([]string{"Accept", "Accept-Language", "Content-Language", "Content-Type"}, c.Headers...)
	requested := r.Header.Get("Access-Control-Request-Headers")
	if slices.Contains(c.Headers, "*") {
		h.Set("Access-Control-Allow-Headers", requested)
	} else {
		for _, raw := range strings.Split(requested, ",") {
			name := strings.TrimSpace(raw)
			if name != "" && !slices.ContainsFunc(hs, func(s string) bool { return strings.EqualFold(name, s) }) {
				ok = false
			}
		}
		h.Set("Access-Control-Allow-Headers", strings.Join(hs, ", "))
	}
	h.Set("Access-Control-Allow-Methods", strings.Join(methods, ", "))
	h.Set("Access-Control-Max-Age", strconv.Itoa(c.MaxAge))
	if !ok {
		http.Error(w, "Disallowed CORS request", 400)
	} else {
		w.WriteHeader(200)
	}
	return true
}
func (a *API) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	rw := &recorder{w, 200}
	id := uuid.NewString()
	rw.Header().Set("X-Request-ID", id)
	slog.Info("http.received", "call", id, "method", r.Method)
	defer func() { slog.Info("http.response", "call", id, "route", r.Pattern, "status", rw.status) }()
	if strings.HasPrefix(r.URL.Path, apiBase+"/") {
		rw.Header().Set("Cache-Control", "no-store")
	}
	if !allowedHost(r.Host, a.cfg.Hosts) {
		http.Error(rw, "Invalid host header", 400)
		return
	}
	if cors(rw, r, a.cfg.CORS) {
		return
	}
	a.mux.ServeHTTP(rw, r)
}
