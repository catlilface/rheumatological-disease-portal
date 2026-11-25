package application

import "portal/bff/internal/domain"

// Community is the inbound port for publication and moderation. The HTTP adapter
// cannot publish a submission or inspect the moderation queue by bypassing a decision.
type Community struct {
	forum   *domain.Forum
	runtime Runtime
}

func NewCommunity(rt Runtime) *Community {
	return &Community{forum: domain.NewForum(rt.ID(), rt.Now()), runtime: rt}
}
func (s Community) Topics(w domain.Window) domain.Page[domain.Message] { return s.forum.Topics(w) }
func (s Community) Topic(id string) (domain.Message, error)            { return s.forum.Topic(id) }
func (s Community) Posts(id string, w domain.Window) (domain.Page[domain.Message], error) {
	return s.forum.Posts(id, w)
}
func (s Community) Cases(a *domain.Actor, w domain.Window) (domain.Page[domain.Case], error) {
	if err := a.RequireModerator(); err != nil {
		return domain.Page[domain.Case]{}, err
	}
	return s.forum.Cases(w), nil
}
func (s Community) Submit(a *domain.Actor, topic, title, body string) ([]domain.Resource, error) {
	if err := a.RequireRegistered(); err != nil {
		return nil, err
	}
	return s.forum.Submit(topic, title, body, s.runtime.Now(), s.runtime.ID)
}
func (s Community) Flag(a *domain.Actor, t domain.Target, reason string) ([]domain.Resource, error) {
	if err := a.RequireRegistered(); err != nil {
		return nil, err
	}
	return s.forum.Flag(t, reason, s.runtime.ID())
}
func (s Community) Decide(a *domain.Actor, id string, x domain.Decision) ([]domain.Resource, error) {
	if err := a.RequireModerator(); err != nil {
		return nil, err
	}
	return s.forum.Decide(id, x)
}
