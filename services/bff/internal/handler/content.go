package handler

func (a *API) Content(content Publications) {
	a.on(opGetArticle, public, func(c *call) (any, error) { return content.Article(c.id("slug")) })
	a.on(opGetDoctorRoute, public, func(c *call) (any, error) { return content.DoctorRoute(), nil })
	a.on(opListArticles, public, func(c *call) (any, error) {
		return content.List(c.optional("disease_tag"), c.optional("section"), c.window), nil
	})
}
