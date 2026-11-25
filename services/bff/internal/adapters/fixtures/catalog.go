package fixtures

import (
	"embed"
	"encoding/json"

	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

//go:embed *.json screening.pdf
var data embed.FS

type Catalog struct {
	Survey   domain.Survey
	PDF      []byte
	articles []application.Article
	route    application.DoctorRoute
}

func Load() (Catalog, error) {
	var c Catalog
	for name, dest := range map[string]any{"survey.json": &c.Survey, "articles.json": &c.articles, "doctor_route.json": &c.route} {
		b, err := data.ReadFile(name)
		if err != nil {
			return c, err
		}
		if err = json.Unmarshal(b, dest); err != nil {
			return c, err
		}
	}
	if err := c.Survey.Validate(); err != nil {
		return c, err
	}
	var err error
	c.PDF, err = data.ReadFile("screening.pdf")
	return c, err
}
func (c Catalog) Articles() []application.Article      { return c.articles }
func (c Catalog) DoctorRoute() application.DoctorRoute { return c.route }
