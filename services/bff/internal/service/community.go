package service

import "portal/bff/internal/models"

// Community is the inbound port for publication and moderation. The HTTP adapter
// cannot publish a submission or inspect the moderation queue by bypassing a decision.
type Community struct {
	forum   *models.Forum
	runtime Runtime
}

func NewCommunity(rt Runtime) *Community {
	return &Community{forum: models.NewForum(rt.ID(), rt.Now()), runtime: rt}
}

func (s Community) Topics(w models.Window) models.Page[models.Message] { return s.forum.Topics(w) }
func (s Community) Topic(id string) (models.Message, error)            { return s.forum.Topic(id) }
func (s Community) Posts(id string, w models.Window) (models.Page[models.Message], error) {
	return s.forum.Posts(id, w)
}

func (s Community) Cases(a *models.Actor, w models.Window) (models.Page[models.Case], error) {
	if err := a.RequireModerator(); err != nil {
		return models.Page[models.Case]{}, err
	}
	return s.forum.Cases(w), nil
}

func (s Community) Submit(a *models.Actor, topic, title, body string) ([]models.Resource, error) {
	if err := a.RequireRegistered(); err != nil {
		return nil, err
	}
	return s.forum.Submit(topic, title, body, s.runtime.Now(), s.runtime.ID)
}

func (s Community) Flag(a *models.Actor, t models.Target, reason string) ([]models.Resource, error) {
	if err := a.RequireRegistered(); err != nil {
		return nil, err
	}
	return s.forum.Flag(t, reason, s.runtime.ID())
}

func (s Community) Decide(a *models.Actor, id string, x models.Decision) ([]models.Resource, error) {
	if err := a.RequireModerator(); err != nil {
		return nil, err
	}
	return s.forum.Decide(id, x)
}
