package config

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

func TestSettings(t *testing.T) {
	dir := t.TempDir()
	s, err := Load(dir)
	if err != nil || s.Name != "Rheumatological Disease Portal" || s.Debug || s.CORS.MaxAge != 600 || len(s.CORS.Origins) != 0 {
		t.Fatalf("unexpected defaults: %v", err)
	}
	file := `APP_NAME="Тестовый портал"
DEBUG=true
UNRELATED=ignored
ALLOWED_HOSTS=["file.test"]
CORS__ALLOW_ORIGINS=["https://site.test"]
CORS__MAX_AGE=120
`
	if err = os.WriteFile(filepath.Join(dir, ".env"), []byte(file), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("ALLOWED_HOSTS", `["env.test"]`)
	t.Setenv("CORS__MAX_AGE", "10")
	s, err = Load(dir)
	if err != nil || s.Name != "Тестовый портал" || !s.Debug || !reflect.DeepEqual(s.Hosts, []string{"env.test"}) || s.CORS.MaxAge != 10 || !reflect.DeepEqual(s.CORS.Origins, []string{"https://site.test"}) {
		t.Fatalf("file/environment precedence: %v", err)
	}
}

func TestNestedCORSOverridesJSON(t *testing.T) {
	t.Setenv("CORS", `{"allow_origins":["https://site.test"],"max_age":120}`)
	t.Setenv("CORS__MAX_AGE", "900")
	s, err := Load(t.TempDir())
	if err != nil || s.CORS.MaxAge != 900 || len(s.CORS.Origins) != 1 {
		t.Fatal(err)
	}
}

func TestHTTPAndDemoSettings(t *testing.T) {
	t.Setenv("BFF_HTTP_ADDR", "127.0.0.1:8080")
	t.Setenv("BFF_HTTP_SHUTDOWN_TIMEOUT", "2s")
	t.Setenv("BFF_HTTP_MAX_BODY_BYTES", "8192")
	t.Setenv("MOCK_SESSION_TTL", "30m")
	t.Setenv("MOCK_REPORT_SHARE_TTL", "12h")
	t.Setenv("MOCK_MODERATOR_EMAIL", "Editor@Example.Test")
	t.Setenv("MOCK_EXPLANATION_SOURCE", "example-article")

	cfg, err := Load(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if cfg.HTTP.Address != "127.0.0.1:8080" || cfg.HTTP.ShutdownTimeout != 2*time.Second ||
		cfg.HTTP.MaxBodyBytes != 8192 {
		t.Fatalf("unexpected HTTP settings: %+v", cfg.HTTP)
	}
	if cfg.Demo.SessionTTL != 30*time.Minute || cfg.Demo.ReportShareTTL != 12*time.Hour ||
		cfg.Demo.ModeratorEmail != "editor@example.test" || cfg.Demo.ExplanationSource != "example-article" {
		t.Fatalf("unexpected demo settings: %+v", cfg.Demo)
	}
}

func TestInvalidSettingsAreRejected(t *testing.T) {
	for k, v := range map[string]string{"DEBUG": "bad", "CORS__MAX_AGE": "-1", "ALLOWED_HOSTS": "[]", "CORS__ALLOW_ORIGINS": `["*"]`, "CORS__ALLOW_METHODS": `["*"]`, "CORS__ALLOW_HEADERS": `["*"]`} {
		t.Run(k, func(t *testing.T) {
			t.Setenv("CORS__ALLOW_CREDENTIALS", "true")
			t.Setenv(k, v)
			if _, err := Load(t.TempDir()); err == nil {
				t.Fatal("accepted invalid config")
			}
		})
	}
}

func TestRootSettingsRelativeToCheckout(t *testing.T) {
	dir := t.TempDir()
	service := filepath.Join(dir, "services/bff")
	spec := filepath.Join(dir, "contracts/http")
	for _, p := range []string{service, spec} {
		if err := os.MkdirAll(p, 0700); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(spec, "bff-v1.openapi.yaml"), nil, 0600); err != nil {
		t.Fatal(err)
	}
	t.Chdir(service)
	root, err := Root()
	if err != nil {
		t.Fatal(err)
	}
	want, _ := filepath.EvalSymlinks(dir)
	got, _ := filepath.EvalSymlinks(root)
	if got != want {
		t.Fatalf("root=%s want=%s", got, want)
	}
}
