package application

import "portal/bff/internal/domain"

type Reviewed struct {
	Title    string `json:"title"`
	Version  int    `json:"version"`
	Reviewer struct {
		Name string `json:"display_name"`
	} `json:"reviewer"`
	PublishedAt string `json:"published_at"`
}
type Summary struct {
	Reviewed
	Slug    string `json:"slug"`
	Section string `json:"section"`
	Summary string `json:"summary"`
	Tag     string `json:"disease_tag,omitempty"`
}
type Source struct {
	Title string `json:"title"`
	URL   string `json:"url"`
}
type Article struct {
	Summary
	Template string   `json:"template_version"`
	Body     string   `json:"body_markdown"`
	Sources  []Source `json:"sources"`
}
type DoctorRoute struct {
	Reviewed
	Body    string   `json:"body_markdown"`
	Sources []Source `json:"sources"`
}
type Library interface {
	Articles() []Article
	DoctorRoute() DoctorRoute
}
type Content struct{ Library Library }

func (s Content) List(tag, section *string, w domain.Window) domain.Page[Summary] {
	var rows []Summary
	for _, a := range s.Library.Articles() {
		if tag != nil && (a.Tag != *tag || a.Tag == "") {
			continue
		}
		if section == nil || a.Section == *section {
			rows = append(rows, a.Summary)
		}
	}
	return domain.Paginate(rows, w)
}
func (s Content) DoctorRoute() DoctorRoute { return s.Library.DoctorRoute() }

func (s Content) Article(slug string) (Article, error) {
	for _, a := range s.Library.Articles() {
		if a.Slug == slug {
			return a, nil
		}
	}
	return Article{}, domain.NotFound()
}
