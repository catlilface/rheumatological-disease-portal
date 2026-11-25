package httpapi

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"slices"
	"strconv"
	"unicode/utf8"

	"github.com/google/uuid"

	"portal/bff/internal/application"
	"portal/bff/internal/config"
	"portal/bff/internal/domain"
)

type API struct {
	cfg      config.Settings
	mux      *http.ServeMux
	pending  contract
	tx       application.UnitOfWork
	auth     Identity
	commands Operations
}

func New(cfg config.Settings, files fs.FS, tx application.UnitOfWork, auth Identity, commands Operations) (*API, error) {
	spec, err := loadContract(files)
	if err != nil {
		return nil, err
	}
	a := &API{cfg, http.NewServeMux(), spec, tx, auth, commands}
	a.mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	a.reference(files)
	a.identity()
	return a, nil
}
func (a *API) Ready() error {
	for id := range a.pending {
		return fmt.Errorf("missing handler: %s", id)
	}
	return nil
}

type access int

const (
	public access = iota
	current
	registered
	member
	moderator
)

type call struct {
	login                       *application.Login
	actor                       *domain.Actor
	values                      map[string]string
	body                        []byte
	fingerprint                 [32]byte
	origin                      string
	accessCookie, refreshCookie string
	window                      domain.Window
	header                      http.Header
	status                      int
}
type handler func(*call) (any, error)
type pdf struct {
	filename string
	data     []byte
}
type badField struct{ field string }

func (e badField) Error() string { return "invalid " + e.field }
func invalid(field string) error { return badField{field} }
func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
func problem(w http.ResponseWriter, err error) {
	code, msg, status := "INTERNAL_ERROR", "Internal error", 500
	var p *domain.Problem
	var field badField
	v := map[string]any{"request_id": w.Header().Get("X-Request-ID")}
	switch {
	case errors.Is(err, errJSON):
		status, code, msg = 400, "INVALID_JSON", "Некорректный запрос."
	case errors.As(err, &field):
		status, code, msg = 422, "VALIDATION_ERROR", "Некорректный запрос."
		v["fields"] = []map[string]string{{"field": field.field, "code": "invalid"}}
	case errors.As(err, &p):
		status = map[domain.Kind]int{domain.Invalid: 422, domain.Missing: 404, domain.Conflict: 409, domain.Unauthenticated: 401, domain.Forbidden: 403, domain.Gone: 410}[p.Kind]
		code, msg = p.Code, p.Message
	}
	v["code"], v["message"] = code, msg
	writeJSON(w, status, v)
}

var errJSON = errors.New("invalid json")

func readBody(w http.ResponseWriter, r *http.Request) ([]byte, any, error) {
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		return nil, nil, invalid("body")
	}
	if len(raw) == 0 {
		return nil, nil, nil
	}
	if !utf8.Valid(raw) || !json.Valid(raw) {
		return nil, nil, errJSON
	}
	var v any
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if err = d.Decode(&v); err != nil {
		return nil, nil, errJSON
	}
	return raw, v, nil
}
func cookie(r *http.Request, key string) string {
	c, err := r.Cookie(key)
	if err != nil {
		return ""
	}
	return c.Value
}
func (a *API) prepare(w http.ResponseWriter, r *http.Request, e endpoint) (*call, error) {
	c := &call{status: 200, header: w.Header(), values: map[string]string{}, window: domain.Window{Limit: 20}, origin: r.Header.Get("Origin"), accessCookie: cookie(r, "portal_session"), refreshCookie: cookie(r, "portal_refresh")}
	if r.Method != "GET" && r.Method != "HEAD" {
		scheme := "http"
		if r.TLS != nil {
			scheme = "https"
		}
		trusted := c.origin == scheme+"://"+r.Host || (c.origin != "" && c.origin != "*" && slices.Contains(a.cfg.CORS.Origins, c.origin))
		if !trusted || r.Header.Get("X-Portal-Request") != "1" {
			return nil, domain.Fail(domain.Forbidden, "BROWSER_REQUEST_DENIED")
		}
	}
	q := r.URL.Query()
	for _, p := range e.params {
		var s string
		var exists bool
		switch p.In {
		case "header":
			s = r.Header.Get(p.Name)
			exists = s != ""
		case "query":
			s = q.Get(p.Name)
			exists = q.Has(p.Name)
		case "path":
			s = r.PathValue(p.Name)
			exists = true
		}
		if !exists && !p.Required {
			continue
		}
		field := p.In + "." + p.Name
		var v any = s
		switch p.scalar {
		case "integer":
			n, err := strconv.Atoi(s)
			if err != nil {
				return nil, invalid(field)
			}
			v = n
			if p.Name == "limit" {
				c.window.Limit = n
			}
			if p.Name == "offset" {
				c.window.Offset = n
			}
		case "boolean":
			b, err := strconv.ParseBool(s)
			if err != nil {
				return nil, invalid(field)
			}
			v = b
			s = strconv.FormatBool(b)
		case "uuid":
			id, err := uuid.Parse(s)
			if err != nil {
				return nil, invalid(field)
			}
			s = id.String()
			v = s
		}
		if p.checked.Validate(v) != nil {
			return nil, invalid(field)
		}
		c.values[p.Name] = s
	}
	if r.Method != "GET" && r.Method != "HEAD" {
		raw, v, err := readBody(w, r)
		if err != nil {
			return nil, err
		}
		if e.body != nil && e.body.Validate(v) != nil {
			return nil, invalid("body")
		}
		var canon []byte
		if raw != nil {
			canon, err = json.Marshal(v)
			if err != nil {
				return nil, err
			}
		}
		// Decode typed input from exactly the document that passed schema validation.
		if e.body != nil {
			c.body = canon
		}
		c.fingerprint = sha256.Sum256([]byte(r.Method + ":" + r.URL.EscapedPath() + ":" + string(canon)))
	}
	return c, nil
}
func (a *API) authorize(c *call, level access) error {
	if level == public {
		return nil
	}
	l, err := a.auth.Session(c.accessCookie)
	if err != nil {
		return err
	}
	c.login, c.actor = l, l.Actor
	if level >= registered {
		if err := c.actor.RequireRegistered(); err != nil {
			return err
		}
	}
	if level == member {
		return c.actor.RequirePatient()
	}
	if level == moderator {
		return c.actor.RequireModerator()
	}
	return nil
}
func (a *API) on(id string, level access, h handler) {
	e, ok := a.pending[id]
	if !ok {
		panic("unknown or duplicate handler: " + id)
	}
	delete(a.pending, id)
	a.mux.HandleFunc(e.pattern, func(w http.ResponseWriter, r *http.Request) {
		c, err := a.prepare(w, r, e)
		if err != nil {
			problem(w, err)
			return
		}
		var data []byte
		var contentType string
		// Copy the response snapshot before releasing the transaction; never hold it during socket I/O.
		a.tx.Within(func() {
			if err = a.authorize(c, level); err != nil {
				return
			}
			var out any
			out, err = h(c)
			if err != nil {
				return
			}
			switch v := out.(type) {
			case pdf:
				contentType = "application/pdf"
				c.header.Set("Content-Disposition", `attachment; filename="`+v.filename+`"`)
				data = v.data
			case nil:
			default:
				contentType = "application/json"
				data, err = json.Marshal(v)
			}
		})
		if err != nil {
			problem(w, err)
			return
		}
		if contentType != "" {
			w.Header().Set("Content-Type", contentType)
		}
		w.WriteHeader(c.status)
		if len(data) > 0 {
			_, _ = w.Write(data)
		}
	})
}
func bind[T any](h func(*call, T) (any, error)) handler {
	return func(c *call) (any, error) {
		var v T
		if len(c.body) > 0 {
			if err := json.Unmarshal(c.body, &v); err != nil {
				return nil, invalid("body")
			}
		}
		if x, ok := any(v).(interface{ Validate() error }); ok {
			if err := x.Validate(); err != nil {
				return nil, err
			}
		}
		return h(c, v)
	}
}

type empty struct{}

func command[T any](a *API, id string, level access, owner string, apply func(*call, T) ([]domain.Resource, error)) {
	a.on(id, level, bind(func(c *call, v T) (any, error) {
		return a.accept(c, owner, func() ([]domain.Resource, error) { return apply(c, v) })
	}))
}
func (a *API) accept(c *call, owner string, apply func() ([]domain.Resource, error)) (any, error) {
	key, err := a.commands.Run(c.actor.ID, owner, c.values["Idempotency-Key"], c.fingerprint, apply)
	if err != nil {
		return nil, err
	}
	url := apiBase + "/operations/" + key.Owner + "/" + key.ID
	c.header.Set("Location", url)
	c.status = 202
	return map[string]string{"operation_id": key.ID, "status_url": url}, nil
}
func (c *call) id(name string) string { return c.values[name] }
func (c *call) version() int          { n, _ := strconv.Atoi(c.values["version"]); return n }
func (c *call) optional(name string) *string {
	v, ok := c.values[name]
	if !ok {
		return nil
	}
	return &v
}
