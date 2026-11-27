package service

import "portal/bff/internal/models"

type Reviewed = models.Reviewed

type Summary = models.Summary

type Source = models.Source

type Article = models.Article

type DoctorRoute = models.DoctorRoute

type Library interface {
	Articles() []Article
	DoctorRoute() DoctorRoute
}

type Content struct{ Library Library }

func (s Content) List(tag, section *string, w models.Window) models.Page[Summary] {
	var rows []Summary
	for _, a := range s.Library.Articles() {
		if tag != nil && (a.Tag != *tag || a.Tag == "") {
			continue
		}
		if section == nil || a.Section == *section {
			rows = append(rows, a.Summary)
		}
	}
	return models.Paginate(rows, w)
}

func (s Content) DoctorRoute() DoctorRoute { return s.Library.DoctorRoute() }

func (s Content) Article(slug string) (Article, error) {
	for _, a := range s.Library.Articles() {
		if a.Slug == slug {
			return a, nil
		}
	}
	return Article{}, models.NotFound()
}
