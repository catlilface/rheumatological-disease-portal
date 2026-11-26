package httpapi

import (
	"encoding/json"

	"portal/bff/internal/domain"
)

// The remaining OpenAPI operations describe the isolated demonstration / future APIs.
// Empty means a public or session-lifecycle operation (no domain resource).
var mvpResources = map[string]string{
	"setAccountRole": "", "registerPatient": "", "withdrawMedicalConsent": "",
	"getOnboarding": "cabinet", "finishOnboarding": "cabinet", "listScreeningResults": "cabinet",
	"listMedications": "cabinet", "addMedication": "cabinet", "updateMedication": "cabinet", "stopMedication": "cabinet",
	"listDoses": "cabinet", "markIntake": "cabinet", "getReminderSettings": "cabinet", "updateReminderSettings": "cabinet",
	"listNotifications": "cabinet", "readNotification": "cabinet", "listDiaryEntries": "cabinet", "getDiaryEntry": "cabinet",
	"createDiaryEntry": "cabinet", "replaceDiaryEntry": "cabinet", "deleteDiaryEntry": "cabinet",
	"createGuestSession": "", "getPrincipal": "", "signIn": "", "signOut": "", "refreshSession": "",
	"getMedicalDataPolicy": "", "getSurvey": "", "listArticles": "", "getArticle": "", "getDoctorRoute": "",
	"startScreening": "subject", "getScreening": "screening", "saveAnswer": "screening",
	"continueAfterRedFlag": "screening", "completeScreening": "screening", "abandonScreening": "screening",
	"getLatestResult": "screening", "getExactResult": "result", "getExplanation": "result", "requestExplanation": "result",
	"requestPdf": "report-source",
	"getReport":  "report", "downloadOwnPdf": "report", "getOperation": "operation",
}

// Resolve ownership in the BFF's synthetic stores. A URL or result reference
// selects a target, never its owner. A miss still gets an audited IAM denial.
func (a *API) resolveResource(c *call, id string) (domain.Resource, error) {
	var r domain.Resource
	var lookup error
	switch mvpResources[id] {
	case "cabinet":
		r = domain.Ref("cabinet", c.actor.ID)
	case "subject":
		r = domain.Ref("subject", c.actor.ID)
	case "screening":
		key := c.owned("screening_id")
		r = domain.Ref("screening", key.ID)
		_, lookup = a.screenings.Get(key)
	case "report-source":
		var spec domain.ReportRequest
		if err := json.Unmarshal(c.body, &spec); err != nil {
			return r, invalid("body")
		}
		if spec.Kind == "doctor" {
			return domain.Ref("cabinet", c.actor.ID), nil
		}
		if spec.Result == nil {
			return r, invalid("body.result")
		}
		return a.resultResource(c.actor.ID, *spec.Result)
	case "result":
		return a.resultResource(c.actor.ID, c.result())
	case "report":
		r = domain.Ref("report", c.id("report_id"))
		var report domain.Report
		report, lookup = a.reports.Find(c.actor.ID, r.ID)
		if lookup == nil && report.Specification.Kind == "doctor" {
			r.Type = "doctor_report"
		}
	case "operation":
		r = domain.Ref("operation", c.id("operation_id"))
		if c.id("owner") == "cabinet" {
			r.Type = "cabinet_operation"
		}
		_, lookup = a.commands.Get(c.actor, c.id("owner"), r.ID)
	default:
		return r, domain.NotFound()
	}
	return r, lookup
}

func (a *API) resultResource(owner string, ref domain.ResultRef) (domain.Resource, error) {
	_, err := a.screenings.Exact(owner, ref)
	return domain.Ref("result", ref.ID, ref.Version), err
}

func (a *API) checkResource(c *call, id string) error {
	var r domain.Resource
	var lookup error
	a.tx.Within(func() { r, lookup = a.resolveResource(c, id) })
	if r.ID == "" {
		return lookup
	}
	owner := ""
	if lookup == nil {
		owner = c.actor.ID
	}
	var err error
	c.validUntil, err = a.auth.Check(c.ctx, c.login, id, r, owner)
	if err != nil {
		return err
	}
	return lookup
}
