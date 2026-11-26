package httpapi

import (
	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

func (c *call) owned(param string) application.OwnedID {
	return application.OwnedID{Owner: c.actor.ID, ID: c.id(param)}
}
func (c *call) result() domain.ResultRef {
	return domain.ResultRef{ID: c.id("result_id"), Version: c.version()}
}
func (a *API) Screening(s Screenings) {
	a.screenings = s
	a.on("getSurvey", public, func(c *call) (any, error) { return s.Survey(c.id("survey_id"), c.optional("weights_version")) })
	command(a, "startScreening", current, "screening", func(c *call, x application.Start) ([]domain.Resource, error) { return s.Start(c.actor.ID, x) })
	a.on("getScreening", current, func(c *call) (any, error) { return s.Get(c.owned("screening_id")) })
	command(a, "saveAnswer", current, "screening", func(c *call, x application.Answer) ([]domain.Resource, error) {
		return s.Answer(c.owned("screening_id"), x)
	})
	for id, apply := range map[string]func(application.OwnedID, application.Revision) ([]domain.Resource, error){"continueAfterRedFlag": s.Continue, "completeScreening": s.Complete, "abandonScreening": s.Abandon} {
		command(a, id, current, "screening", func(c *call, x application.Revision) ([]domain.Resource, error) {
			return apply(c.owned("screening_id"), x)
		})
	}
	a.on("getLatestResult", current, func(c *call) (any, error) { return s.Latest(c.owned("screening_id")) })
	a.on("getExactResult", current, func(c *call) (any, error) { return s.Exact(c.actor.ID, c.result()) })
	command(a, "requestExplanation", current, "ai", func(c *call, _ empty) ([]domain.Resource, error) {
		return s.Explain(c.actor.ID, c.result())
	})
	a.on("getExplanation", current, func(c *call) (any, error) { return s.Explanation(c.actor.ID, c.result()) })

}
