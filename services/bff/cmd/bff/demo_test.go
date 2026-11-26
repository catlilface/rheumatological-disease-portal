package main

// The old synthetic patient/cabinet contract tests run in this test binary only.
// No environment variable or flag in the deployed binary enables local identity.
import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"portal/bff/internal/adapters/credentials"
	"portal/bff/internal/adapters/httpapi"
	"portal/bff/internal/adapters/memory"
	app "portal/bff/internal/application"
	"portal/bff/internal/config"
	"portal/bff/internal/domain"
)

type demoAuth struct{ s app.Identity }

func (d demoAuth) Guest(_ context.Context, key, cookie string) (*app.Login, error) {
	return d.s.Guest(key, cookie)
}
func (d demoAuth) Rotate(_ context.Context, refresh, key string) (*app.Login, error) {
	return d.s.Rotate(refresh, key)
}
func (d demoAuth) SignIn(_ context.Context, email, password string) (*app.Login, error) {
	return d.s.SignIn(email, password)
}
func (d demoAuth) Session(_ context.Context, cookie string) (*app.Login, error) {
	return d.s.Session(cookie)
}
func (d demoAuth) Revoke(_ context.Context, token string) error {
	l, err := d.s.Session(token)
	if err == nil {
		d.s.Revoke(l)
	}
	return err
}
func (d demoAuth) Check(context.Context, *app.Login, string, domain.Resource, string) error {
	panic("not an IAM client")
}
func demo(cfg config.Settings) (httpapi.Identity, httpapi.DemoRegistration, error) {
	s := app.Identity{Runtime: app.Runtime{Now: time.Now, ID: uuid.NewString, Token: uuid.NewString}, Access: memory.New[string, *app.Login](), Refreshes: memory.New[string, *app.Login](), Accounts: memory.New[string, app.Account](), Retries: memory.New[app.ReplayKey, *app.Login](), Passwords: credentials.Scrypt{}, ModeratorPassword: cfg.ModeratorPassword}
	return demoAuth{s}, s.Register, nil
}
func buildDemo(root string, cfg config.Settings) (http.Handler, error) {
	auth, reg, _ := demo(cfg)
	return build(root, cfg, auth, reg)
}
func TestMain(m *testing.M) {
	if os.Getenv("BFF_CONTRACT_TEST_SERVER") == "1" {
		if err := run(demo); err != nil {
			panic(err)
		}
		return
	}
	os.Exit(m.Run())
}
