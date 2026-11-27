package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

const (
	ContractDir = "contracts/http"
	OpenAPIFile = "bff-v1.openapi.yaml"
	SchemaFile  = "schemas.yaml"
)

type HTTP struct {
	Address           string
	ReadHeaderTimeout time.Duration
	ReadTimeout       time.Duration
	WriteTimeout      time.Duration
	IdleTimeout       time.Duration
	ShutdownTimeout   time.Duration
	MaxBodyBytes      int64
}

type Demo struct {
	ModeratorEmail    string
	ExplanationSource string
	SessionTTL        time.Duration
	ReportShareTTL    time.Duration
}

type CORS struct {
	Origins     []string `json:"allow_origins"`
	Methods     []string `json:"allow_methods"`
	Headers     []string `json:"allow_headers"`
	Credentials bool     `json:"allow_credentials"`
	Expose      []string `json:"expose_headers"`
	MaxAge      int      `json:"max_age"`
}

type Settings struct {
	Name, ModeratorPassword string
	Debug                   bool
	Hosts                   []string
	CORS                    CORS
	HTTP                    HTTP
	Demo                    Demo
	Delivery                Delivery
}

func Defaults() Settings {
	return Settings{
		Name:  "Rheumatological Disease Portal",
		Hosts: []string{"localhost", "127.0.0.1", "bff", "server"},
		CORS:  CORS{Methods: []string{http.MethodGet}, MaxAge: 600},
		HTTP: HTTP{
			Address:           ":8000",
			ReadHeaderTimeout: 5 * time.Second,
			ReadTimeout:       15 * time.Second,
			WriteTimeout:      30 * time.Second,
			IdleTimeout:       time.Minute,
			ShutdownTimeout:   10 * time.Second,
			MaxBodyBytes:      1 << 20,
		},
		Demo: Demo{
			ModeratorEmail:    "moderator@example.test",
			ExplanationSource: "rheumatoid-arthritis",
			SessionTTL:        24 * time.Hour,
			ReportShareTTL:    24 * time.Hour,
		},
	}
}

func Root() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for dir := cwd; ; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, ContractDir, OpenAPIFile)); err == nil {
			return dir, nil
		}
		if dir == filepath.Dir(dir) {
			return "", errors.New("contracts/http not found; start from the repository or image working directory")
		}
	}
}

func Load(root string) (Settings, error) {
	s := Defaults()
	file, err := godotenv.Read(filepath.Join(root, ".env"))
	if err != nil && !os.IsNotExist(err) {
		return s, errors.New("invalid .env")
	}
	env := environment()
	for _, source := range []map[string]string{file, env} {
		if err := s.apply(source); err != nil {
			return s, err
		}
	}
	if len(s.Hosts) == 0 || s.CORS.MaxAge < 0 {
		return s, errors.New("invalid host list or CORS max age")
	}
	if s.CORS.Credentials && (slices.Contains(s.CORS.Origins, "*") || slices.Contains(s.CORS.Methods, "*") || slices.Contains(s.CORS.Headers, "*")) {
		return s, errors.New("credentialed CORS forbids wildcards")
	}
	for key, value := range file {
		if _, ok := env[key]; !ok {
			env[key] = value
		}
	}
	s.Delivery, err = deliverySettings(env)
	return s, err
}

func (s *Settings) apply(source map[string]string) error {
	for key, dest := range map[string]*string{
		"APP_NAME":                &s.Name,
		"MOCK_MODERATOR_PASSWORD": &s.ModeratorPassword,
		"MOCK_MODERATOR_EMAIL":    &s.Demo.ModeratorEmail,
		"MOCK_EXPLANATION_SOURCE": &s.Demo.ExplanationSource,
		"BFF_HTTP_ADDR":           &s.HTTP.Address,
	} {
		if value, ok := source[key]; ok {
			*dest = value
		}
	}
	if s.HTTP.Address == "" || s.Demo.ModeratorEmail == "" || s.Demo.ExplanationSource == "" {
		return errors.New("listen address, moderator email and explanation source must be non-empty")
	}
	s.Demo.ModeratorEmail = strings.ToLower(s.Demo.ModeratorEmail)
	for key, dest := range map[string]*time.Duration{
		"BFF_HTTP_READ_HEADER_TIMEOUT": &s.HTTP.ReadHeaderTimeout,
		"BFF_HTTP_READ_TIMEOUT":        &s.HTTP.ReadTimeout,
		"BFF_HTTP_WRITE_TIMEOUT":       &s.HTTP.WriteTimeout,
		"BFF_HTTP_IDLE_TIMEOUT":        &s.HTTP.IdleTimeout,
		"BFF_HTTP_SHUTDOWN_TIMEOUT":    &s.HTTP.ShutdownTimeout,
		"MOCK_SESSION_TTL":             &s.Demo.SessionTTL,
		"MOCK_REPORT_SHARE_TTL":        &s.Demo.ReportShareTTL,
	} {
		if value, ok := source[key]; ok {
			duration, err := time.ParseDuration(value)
			if err != nil || duration <= 0 {
				return fmt.Errorf("invalid %s: expected a positive duration", key)
			}
			*dest = duration
		}
	}
	if value, ok := source["BFF_HTTP_MAX_BODY_BYTES"]; ok {
		size, err := strconv.ParseInt(value, 10, 64)
		if err != nil || size <= 0 {
			return errors.New("invalid BFF_HTTP_MAX_BODY_BYTES: expected a positive integer")
		}
		s.HTTP.MaxBodyBytes = size
	}
	if value, ok := source["CORS"]; ok {
		if err := json.Unmarshal([]byte(value), &s.CORS); err != nil {
			return errors.New("invalid CORS")
		}
	}
	for key, dest := range map[string]*[]string{
		"ALLOWED_HOSTS":        &s.Hosts,
		"CORS__ALLOW_ORIGINS":  &s.CORS.Origins,
		"CORS__ALLOW_METHODS":  &s.CORS.Methods,
		"CORS__ALLOW_HEADERS":  &s.CORS.Headers,
		"CORS__EXPOSE_HEADERS": &s.CORS.Expose,
	} {
		if value, ok := source[key]; ok {
			if err := json.Unmarshal([]byte(value), dest); err != nil {
				return fmt.Errorf("invalid %s", key)
			}
		}
	}
	for key, dest := range map[string]*bool{
		"DEBUG":                   &s.Debug,
		"CORS__ALLOW_CREDENTIALS": &s.CORS.Credentials,
	} {
		if value, ok := source[key]; ok {
			parsed, err := strconv.ParseBool(value)
			if err != nil {
				return fmt.Errorf("invalid %s", key)
			}
			*dest = parsed
		}
	}
	if value, ok := source["CORS__MAX_AGE"]; ok {
		age, err := strconv.Atoi(value)
		if err != nil {
			return errors.New("invalid CORS__MAX_AGE")
		}
		s.CORS.MaxAge = age
	}
	return nil
}

func environment() map[string]string {
	m := map[string]string{}
	for _, item := range os.Environ() {
		k, v, _ := strings.Cut(item, "=")
		m[k] = v
	}
	return m
}
