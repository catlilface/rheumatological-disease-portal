package app

// The old synthetic patient/cabinet contract tests run in this test binary only.
// No environment variable or flag in the deployed binary enables local identity.
import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"

	"portal/bff/cmd/config"
	"portal/bff/internal/models"
	"portal/bff/internal/repo"
	"portal/bff/internal/service"
	"portal/bff/pkg/credentials"
)

type demoAuth struct{ s service.Identity }

func (d demoAuth) Guest(_ context.Context, key, cookie string) (*service.Login, error) {
	return d.s.Guest(key, cookie)
}
func (d demoAuth) Rotate(_ context.Context, refresh, key string) (*service.Login, error) {
	return d.s.Rotate(refresh, key)
}
func (d demoAuth) SignIn(_ context.Context, email, password string) (*service.Login, error) {
	return d.s.SignIn(email, password)
}
func (d demoAuth) Session(_ context.Context, cookie string) (*service.Login, error) {
	return d.s.Session(cookie)
}
func (d demoAuth) WithdrawConsent(_ context.Context, token string) error {
	l, err := d.s.Session(token)
	if err != nil {
		return err
	}
	return l.Actor.WithdrawConsent()
}
func (d demoAuth) Revoke(_ context.Context, token string) error {
	l, err := d.s.Session(token)
	if err == nil {
		d.s.Revoke(l)
	}
	return err
}
func (d demoAuth) Register(_ context.Context, key, _, email, password string, consent service.MedicalConsent) (*service.Login, error) {
	return d.s.Register(key, email, password, consent)
}
func (d demoAuth) SetRole(context.Context, string, string, string) error { return models.NotFound() }
func (d demoAuth) Check(context.Context, *service.Login, string, models.Resource, string) (time.Time, error) {
	panic("not an IAM client")
}
func demo(cfg config.Settings) (dependencies, error) {
	s := service.Identity{
		Runtime:           newRuntime(),
		Access:            repo.New[string, *service.Login](),
		Refreshes:         repo.New[string, *service.Login](),
		Accounts:          repo.New[string, service.Account](),
		Retries:           repo.New[service.ReplayKey, *service.Login](),
		Passwords:         credentials.Scrypt{},
		ModeratorPassword: cfg.ModeratorPassword,
		ModeratorEmail:    cfg.Demo.ModeratorEmail,
		SessionTTL:        cfg.Demo.SessionTTL,
	}
	return dependencies{auth: demoAuth{s}, demo: true}, nil
}

func buildDemo(root string, cfg config.Settings) (http.Handler, error) {
	deps, err := demo(cfg)
	if err != nil {
		return nil, err
	}
	return build(root, cfg, deps)
}

func TestMain(m *testing.M) {
	if os.Getenv("BFF_CONTRACT_TEST_SERVER") == "1" {
		if err := run(os.Args[1:], demo); err != nil {
			panic(err)
		}
		return
	}
	os.Exit(m.Run())
}
