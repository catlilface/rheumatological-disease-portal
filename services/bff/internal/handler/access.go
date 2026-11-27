package handler

import (
	"encoding/json"

	"portal/bff/internal/models"
)

// The remaining OpenAPI operations describe the isolated demonstration / future APIs.
// Empty means a public or session-lifecycle operation (no domain resource).
var mvpResources = map[string]string{
	opSetAccountRole: "", opRegisterPatient: "", opWithdrawMedicalConsent: "",
	opGetOnboarding: "cabinet", opFinishOnboarding: "cabinet", opListScreeningResults: "cabinet",
	opListMedications: "cabinet", "addMedication": "cabinet", "updateMedication": "cabinet", opStopMedication: "cabinet",
	opListDoses: "cabinet", opMarkIntake: "cabinet", opGetReminderSettings: "cabinet", opUpdateReminderSettings: "cabinet",
	opListNotifications: "cabinet", opReadNotification: "cabinet", opListDiaryEntries: "cabinet", opGetDiaryEntry: "cabinet",
	"createDiaryEntry": "cabinet", "replaceDiaryEntry": "cabinet", opDeleteDiaryEntry: "cabinet",
	opCreateGuestSession: "", opGetPrincipal: "", opSignIn: "", opSignOut: "", opRefreshSession: "",
	opGetMedicalDataPolicy: "", opGetSurvey: "", opListArticles: "", opGetArticle: "", opGetDoctorRoute: "",
	opStartScreening: "subject", opGetScreening: "screening", opSaveAnswer: "screening",
	"continueAfterRedFlag": "screening", "completeScreening": "screening", "abandonScreening": "screening",
	opGetLatestResult: "screening", opGetExactResult: "result", opGetExplanation: "result", opRequestExplanation: "result",
	opRequestPdf: "report-source",
	opGetReport:  "report", opDownloadOwnPdf: "report", opGetOperation: "operation",
}

// Resolve ownership in the BFF's synthetic stores. A URL or result reference
// selects a target, never its owner. A miss still gets an audited IAM denial.
func (a *API) resolveResource(c *call, id string) (models.Resource, error) {
	var r models.Resource
	var lookup error
	switch mvpResources[id] {
	case "cabinet":
		r = models.Ref("cabinet", c.actor.ID)
	case "subject":
		r = models.Ref("subject", c.actor.ID)
	case "screening":
		key := c.owned("screening_id")
		r = models.Ref("screening", key.ID)
		_, lookup = a.screenings.Get(key)
	case "report-source":
		var spec models.ReportRequest
		if err := json.Unmarshal(c.body, &spec); err != nil {
			return r, invalid("body")
		}
		if spec.Kind == models.DoctorReport {
			return models.Ref("cabinet", c.actor.ID), nil
		}
		if spec.Result == nil {
			return r, invalid("body.result")
		}
		return a.resultResource(c.actor.ID, *spec.Result)
	case "result":
		return a.resultResource(c.actor.ID, c.result())
	case "report":
		r = models.Ref("report", c.id("report_id"))
		var report models.Report
		report, lookup = a.reports.Find(c.actor.ID, r.ID)
		if lookup == nil && report.Specification.Kind == models.DoctorReport {
			r.Type = "doctor_report"
		}
	case "operation":
		r = models.Ref("operation", c.id("operation_id"))
		if c.id("owner") == "cabinet" {
			r.Type = "cabinet_operation"
		}
		_, lookup = a.commands.Get(c.actor, c.id("owner"), r.ID)
	default:
		return r, models.NotFound()
	}
	return r, lookup
}

func (a *API) resultResource(owner string, ref models.ResultRef) (models.Resource, error) {
	_, err := a.screenings.Exact(owner, ref)
	return models.Ref("result", ref.ID, ref.Version), err
}

func (a *API) checkResource(c *call, id string) error {
	var r models.Resource
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
