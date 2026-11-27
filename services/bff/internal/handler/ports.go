package handler

import (
	"portal/bff/internal/models"
	"portal/bff/internal/service"
	"portal/bff/pkg/idempotency"
)

// Inbound ports are defined by the adapter that consumes them. In particular,
// an HTTP handler gets session and command use cases, not their repositories.
type Identity interface {
	Session(cookie string) (*service.Login, error)
	Guest(key, cookie string) (*service.Login, error)
	Register(key, email, password string, consent service.MedicalConsent) (*service.Login, error)
	SignIn(email, password string) (*service.Login, error)
	Rotate(refresh, key string) (*service.Login, error)
	Revoke(*service.Login)
}

type Operations interface {
	Run(actor, owner, key string, fingerprint idempotency.Fingerprint, apply func() ([]models.Resource, error)) (service.OperationKey, error)
	Get(*models.Actor, string, string) (models.Operation, error)
}

type Screenings interface {
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
