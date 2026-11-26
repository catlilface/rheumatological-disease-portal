package app

import (
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"

	"portal/bff/cmd/config"
	"portal/bff/internal/handler"
	"portal/bff/internal/models"
	"portal/bff/internal/repo"
	"portal/bff/internal/repo/fixtures"
	"portal/bff/internal/service"
	"portal/bff/pkg/credentials"
)

func Build(root string, cfg config.Settings) (http.Handler, error) {
	return build(root, cfg, nil)
}

func build(root string, cfg config.Settings, delivery *deliveryRuntime) (http.Handler, error) {
	catalog, err := fixtures.Load()
	if err != nil {
		return nil, err
	}
	runtime := service.Runtime{
		Now:   func() time.Time { return time.Now().UTC() },
		ID:    func() string { return uuid.Must(uuid.NewV7()).String() },
		Token: credentials.NewToken,
	}
	identity := service.Identity{
		Runtime:           runtime,
		Access:            repo.New[string, *service.Login](),
		Refreshes:         repo.New[string, *service.Login](),
		Accounts:          repo.New[string, service.Account](),
		Retries:           repo.New[service.ReplayKey, *service.Login](),
		Passwords:         credentials.Scrypt{},
		ModeratorPassword: cfg.ModeratorPassword,
		ModeratorEmail:    cfg.Demo.ModeratorEmail,
		SessionTTL:        cfg.Demo.SessionTTL,
	}
	commands := service.Commands{
		Runtime:    runtime,
		Operations: repo.New[service.OperationKey, models.Operation](),
		Receipts:   repo.New[service.IntentKey, service.Receipt](),
	}
	api, err := handler.New(cfg, os.DirFS(filepath.Join(root, config.ContractDir)), &repo.Transactions{}, identity, commands)
	if err != nil {
		return nil, err
	}
	content := service.Content{Library: catalog}
	source, err := content.Article(cfg.Demo.ExplanationSource)
	if err != nil {
		return nil, err
	}
	screening := service.Screening{
		Runtime:           runtime,
		Definition:        catalog.Survey,
		ExplanationSource: service.SourceRef{Slug: source.Slug, Version: source.Version},
		Sessions:          repo.New[service.OwnedID, *models.Session](),
		Results:           repo.New[service.OwnedResult, models.Result](),
		Explanations:      repo.New[service.OwnedResult, service.Explanation](),
	}
	api.Screening(screening)
	api.Content(content)
	api.Cabinet(service.Cabinets{Runtime: runtime, Records: repo.New[string, *models.Cabinet]()})
	api.Community(service.NewCommunity(runtime))
	api.Reports(service.Reports{
		Runtime:  runtime,
		Results:  screening,
		ShareTTL: cfg.Demo.ReportShareTTL,
		Records:  repo.New[service.OwnedID, models.Report](),
		Shares:   repo.New[service.ShareKey, *models.Grant](),
		Tokens:   repo.New[string, *models.Grant](),
	}, catalog.PDF)
	if delivery != nil {
		api.Delivery(delivery.DeliveryDemo, delivery.Transport, delivery.counters)
	}
	return api, api.Ready()
}
