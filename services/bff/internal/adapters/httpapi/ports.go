package httpapi

import (
	"context"
	"time"

	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

// Inbound ports are defined by the adapter that consumes them. In particular,
// an HTTP handler gets session and command use cases, not their repositories.
type Identity interface {
	Register(ctx context.Context, key, access, email, password string, consent application.MedicalConsent) (*application.Login, error)
	SetRole(ctx context.Context, access, email, role string) error
	Session(context.Context, string) (*application.Login, error)
	Guest(ctx context.Context, key, cookie string) (*application.Login, error)
	SignIn(ctx context.Context, email, password string) (*application.Login, error)
	Rotate(ctx context.Context, refresh, key string) (*application.Login, error)
	Revoke(ctx context.Context, access string) error
	Check(ctx context.Context, login *application.Login, action string, resource domain.Resource, owner string) (time.Time, error)
}
type Operations interface {
	Run(actor, owner, key string, fingerprint [32]byte, apply func() ([]domain.Resource, error)) (application.OperationKey, error)
	Get(*domain.Actor, string, string) (domain.Operation, error)
}
type Screenings interface {
	History(string, domain.Window) (domain.Page[domain.Result], error)
	Survey(id string, weightsVersion *string) (domain.Survey, error)
	Start(string, application.Start) ([]domain.Resource, error)
	Get(application.OwnedID) (*domain.Session, error)
	Answer(application.OwnedID, application.Answer) ([]domain.Resource, error)
	Continue(application.OwnedID, application.Revision) ([]domain.Resource, error)
	Complete(application.OwnedID, application.Revision) ([]domain.Resource, error)
	Abandon(application.OwnedID, application.Revision) ([]domain.Resource, error)
	Latest(application.OwnedID) (domain.Result, error)
	application.ResultReader
	Explain(string, domain.ResultRef) ([]domain.Resource, error)
	Explanation(string, domain.ResultRef) (application.Explanation, error)
}
type Publications interface {
	Article(string) (application.Article, error)
	List(tag, section *string, w domain.Window) domain.Page[application.Summary]
	DoctorRoute() application.DoctorRoute
}
