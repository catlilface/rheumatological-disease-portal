package handler

import (
	"portal/bff/internal/models"
	"portal/bff/internal/service"
)

func (a *API) Community(f *service.Community) {
	a.on(opListTopics, public, func(c *call) (any, error) { return f.Topics(c.window), nil })
	a.on(opGetTopic, public, func(c *call) (any, error) { return f.Topic(c.id("topic_id")) })
	a.on(opListPosts, public, func(c *call) (any, error) { return f.Posts(c.id("topic_id"), c.window) })
	a.on(opListModerationCases, moderator, func(c *call) (any, error) { return f.Cases(c.actor, c.window) })
	for _, id := range []string{"submitTopic", "submitPost"} {
		command(a, id, registered, service.OwnerCommunity, func(c *call, x struct{ Title, Body string }) ([]models.Resource, error) {
			return f.Submit(c.actor, c.id("topic_id"), x.Title, x.Body)
		})
	}
	command(a, opFlagContent, registered, service.OwnerCommunity, func(c *call, x struct {
		Target models.Target
		Reason string
	}) ([]models.Resource, error) {
		return f.Flag(c.actor, x.Target, x.Reason)
	})
	command(a, opModerateContent, moderator, service.OwnerCommunity, func(c *call, x models.Decision) ([]models.Resource, error) {
		return f.Decide(c.actor, c.id("case_id"), x)
	})
}
