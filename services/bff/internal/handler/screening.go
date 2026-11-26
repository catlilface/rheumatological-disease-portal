package handler

import (
	"portal/bff/internal/models"
	"portal/bff/internal/service"
)

func (c *call) owned(param string) service.OwnedID {
	return service.OwnedID{Owner: c.actor.ID, ID: c.id(param)}
}

func (c *call) result() models.ResultRef {
	return models.ResultRef{ID: c.id("result_id"), Version: c.version()}
}

func (a *API) Screening(s Screenings) {
	a.on(opGetSurvey, public, func(c *call) (any, error) { return s.Survey(c.id("survey_id"), c.optional("weights_version")) })
	command(a, opStartScreening, current, service.OwnerScreening, func(c *call, x service.Start) ([]models.Resource, error) { return s.Start(c.actor.ID, x) })
	a.on(opGetScreening, current, func(c *call) (any, error) { return s.Get(c.owned("screening_id")) })
	command(a, opSaveAnswer, current, service.OwnerScreening, func(c *call, x service.Answer) ([]models.Resource, error) {
		return s.Answer(c.owned("screening_id"), x)
	})
	revisions := map[string]func(service.OwnedID, service.Revision) ([]models.Resource, error){
		"continueAfterRedFlag": s.Continue,
		"completeScreening":    s.Complete,
		"abandonScreening":     s.Abandon,
	}
	for id, apply := range revisions {
		command(a, id, current, service.OwnerScreening, func(c *call, x service.Revision) ([]models.Resource, error) {
			return apply(c.owned("screening_id"), x)
		})
	}
	a.on(opGetLatestResult, current, func(c *call) (any, error) { return s.Latest(c.owned("screening_id")) })
	a.on(opGetExactResult, current, func(c *call) (any, error) { return s.Exact(c.actor.ID, c.result()) })
	command(a, opRequestExplanation, current, service.OwnerAI, func(c *call, _ empty) ([]models.Resource, error) {
		return s.Explain(c.actor.ID, c.result())
	})
	a.on(opGetExplanation, current, func(c *call) (any, error) { return s.Explanation(c.actor.ID, c.result()) })
}
