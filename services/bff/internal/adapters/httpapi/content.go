package httpapi

func (a *API) Content(content Publications) {
	a.on("getArticle", public, func(c *call) (any, error) { return content.Article(c.id("slug")) })
	a.on("getDoctorRoute", public, func(c *call) (any, error) { return content.DoctorRoute(), nil })
	a.on("listArticles", public, func(c *call) (any, error) {
		return content.List(c.optional("disease_tag"), c.optional("section"), c.window), nil
	})
}
