package httpapi

import (
	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

func (a *API) Reports(s application.Reports, document []byte) {
	a.reports = s
	a.on("requestPdf", current, bind(func(c *call, x domain.ReportRequest) (any, error) {
		if x.Kind == "doctor" {
			if err := c.actor.RequirePatient(); err != nil {
				return nil, err
			}
		}
		return a.accept(c, "reporting", func() ([]domain.Resource, error) { return s.Create(c.actor, x) })
	}))
	a.on("getReport", current, func(c *call) (any, error) {
		r, err := s.Get(c.actor, c.id("report_id"))
		if err != nil {
			return nil, err
		}
		return struct {
			domain.Report
			URL string `json:"download_url"`
		}{r, apiBase + "/reports/" + r.ID + "/pdf"}, nil
	})
	file := func(id string) pdf { return pdf{"report-" + id + ".pdf", document} }
	a.on("downloadOwnPdf", current, func(c *call) (any, error) {
		r, err := s.Get(c.actor, c.id("report_id"))
		if err != nil {
			return nil, err
		}
		return file(r.ID), nil
	})
	command(a, "issueDoctorLink", member, "files", func(c *call, _ empty) ([]domain.Resource, error) {
		return s.Issue(c.actor, c.id("report_id"), c.origin)
	})
	a.on("getDoctorLink", member, func(c *call) (any, error) { return s.Share(c.actor, c.id("report_id"), c.id("share_id")) })
	command(a, "revokeDoctorLink", member, "files", func(c *call, _ empty) ([]domain.Resource, error) {
		return s.Revoke(c.actor, c.id("report_id"), c.id("share_id"))
	})
	a.on("redeemDoctorLink", public, bind(func(c *call, x struct{ Token string }) (any, error) {
		g, err := s.Redeem(x.Token)
		if err != nil {
			return nil, err
		}
		return file(g.Report), nil
	}))
}
