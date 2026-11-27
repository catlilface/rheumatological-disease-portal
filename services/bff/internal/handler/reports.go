package handler

import (
	"portal/bff/internal/models"
	"portal/bff/internal/service"
)

func (a *API) Reports(s service.Reports, document []byte) {
	a.reports = s
	a.on(opRequestPdf, current, bind(func(c *call, x models.ReportRequest) (any, error) {
		if err := s.AuthorizeCreate(c.actor, x); err != nil {
			return nil, err
		}
		return a.accept(c, service.OwnerReporting, func() ([]models.Resource, error) { return s.Create(c.actor, x) })
	}))
	a.on(opGetReport, current, func(c *call) (any, error) {
		r, err := s.Get(c.actor, c.id("report_id"))
		if err != nil {
			return nil, err
		}
		return struct {
			models.Report
			URL string `json:"download_url"`
		}{r, apiBase + "/reports/" + r.ID + "/pdf"}, nil
	})
	file := func(id string) pdf { return pdf{"report-" + id + ".pdf", document} }
	a.on(opDownloadOwnPdf, current, func(c *call) (any, error) {
		r, err := s.Get(c.actor, c.id("report_id"))
		if err != nil {
			return nil, err
		}
		return file(r.ID), nil
	})
	command(a, opIssueDoctorLink, member, service.OwnerFiles, func(c *call, _ empty) ([]models.Resource, error) {
		return s.Issue(c.actor, c.id("report_id"), c.origin)
	})
	a.on(opGetDoctorLink, member, func(c *call) (any, error) { return s.Share(c.actor, c.id("report_id"), c.id("share_id")) })
	command(a, opRevokeDoctorLink, member, service.OwnerFiles, func(c *call, _ empty) ([]models.Resource, error) {
		return s.Revoke(c.actor, c.id("report_id"), c.id("share_id"))
	})
	a.on(opRedeemDoctorLink, public, bind(func(c *call, x struct{ Token string }) (any, error) {
		g, err := s.Redeem(x.Token)
		if err != nil {
			return nil, err
		}
		return file(g.Report), nil
	}))
}
