package handler

import (
	"context"
	"time"

	"portal/bff/internal/models"
	"portal/bff/internal/service"
	"portal/bff/pkg/idempotency"
)

// Inbound ports are defined by the adapter that consumes them. In particular,
// an HTTP handler gets session and command use cases, not their repositories.
type Identity interface {
	Session(ctx context.Context, cookie string) (*service.Login, error)
	Guest(ctx context.Context, key, cookie string) (*service.Login, error)
	Register(ctx context.Context, key, access, email, password string, consent service.MedicalConsent) (*service.Login, error)
	SignIn(ctx context.Context, email, password string) (*service.Login, error)
	Rotate(ctx context.Context, refresh, key string) (*service.Login, error)
	Revoke(ctx context.Context, access string) error
	SetRole(ctx context.Context, access, email, role string) error
	WithdrawConsent(ctx context.Context, access string) error
	Check(ctx context.Context, login *service.Login, action string, resource models.Resource, owner string) (time.Time, error)
}

type Operations interface {
	RunCabinet(*models.Actor, string, idempotency.Fingerprint, service.Cabinets, func(service.PatientCabinet) ([]models.Resource, error)) (service.OperationKey, error)
	Run(actor, owner, key string, fingerprint idempotency.Fingerprint, apply func() ([]models.Resource, error)) (service.OperationKey, error)
	Get(*models.Actor, string, string) (models.Operation, error)
}

type Screenings interface {
	History(string, models.Window) (models.Page[models.Result], error)
	Survey(id string, weightsVersion *string) (models.Survey, error)
	Start(string, service.Start) ([]models.Resource, error)
	Get(service.OwnedID) (*models.Session, error)
	Answer(service.OwnedID, service.Answer) ([]models.Resource, error)
	Continue(service.OwnedID, service.Revision) ([]models.Resource, error)
	Complete(service.OwnedID, service.Revision) ([]models.Resource, error)
	Abandon(service.OwnedID, service.Revision) ([]models.Resource, error)
	Latest(service.OwnedID) (models.Result, error)
	service.ResultReader
	Explain(string, models.ResultRef) ([]models.Resource, error)
	Explanation(string, models.ResultRef) (service.Explanation, error)
}

type Publications interface {
	Article(string) (service.Article, error)
	List(tag, section *string, w models.Window) models.Page[service.Summary]
	DoctorRoute() service.DoctorRoute
}
