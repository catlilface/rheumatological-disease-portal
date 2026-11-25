package httpapi

import (
	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

func (a *API) Community(f *application.Community) {
	a.on("listTopics", public, func(c *call) (any, error) { return f.Topics(c.window), nil })
	a.on("getTopic", public, func(c *call) (any, error) { return f.Topic(c.id("topic_id")) })
	a.on("listPosts", public, func(c *call) (any, error) { return f.Posts(c.id("topic_id"), c.window) })
	a.on("listModerationCases", moderator, func(c *call) (any, error) { return f.Cases(c.actor, c.window) })
	for _, id := range []string{"submitTopic", "submitPost"} {
		command(a, id, registered, "community", func(c *call, x struct{ Title, Body string }) ([]domain.Resource, error) {
			return f.Submit(c.actor, c.id("topic_id"), x.Title, x.Body)
		})
	}
	command(a, "flagContent", registered, "community", func(c *call, x struct {
		Target domain.Target
		Reason string
	}) ([]domain.Resource, error) {
		return f.Flag(c.actor, x.Target, x.Reason)
	})
	command(a, "moderateContent", moderator, "community", func(c *call, x domain.Decision) ([]domain.Resource, error) {
		return f.Decide(c.actor, c.id("case_id"), x)
	})
}
