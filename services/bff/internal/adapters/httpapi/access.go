package httpapi

import (
	"encoding/json"

	"portal/bff/internal/domain"
)

// The remaining OpenAPI operations describe the isolated demonstration / future APIs.
// Empty means a public or session-lifecycle operation (no domain resource).
var mvpResources = map[string]string{
	"setAccountRole": "", "registerPatient": "",
	"getOnboarding": "cabinet", "finishOnboarding": "cabinet", "listScreeningResults": "cabinet",
	"listMedications": "cabinet", "addMedication": "cabinet", "updateMedication": "cabinet", "stopMedication": "cabinet",
	"listDoses": "cabinet", "markIntake": "cabinet", "getReminderSettings": "cabinet", "updateReminderSettings": "cabinet",
	"listNotifications": "cabinet", "readNotification": "cabinet", "listDiaryEntries": "cabinet", "getDiaryEntry": "cabinet",
	"createDiaryEntry": "cabinet", "replaceDiaryEntry": "cabinet", "deleteDiaryEntry": "cabinet",
	"createGuestSession": "", "getPrincipal": "", "signIn": "", "signOut": "", "refreshSession": "",
	"getMedicalDataPolicy": "", "getSurvey": "", "listArticles": "", "getArticle": "", "getDoctorRoute": "",
	"startScreening": "subject", "getScreening": "screening", "saveAnswer": "screening",
	"continueAfterRedFlag": "screening", "completeScreening": "screening", "abandonScreening": "screening",
	"getLatestResult": "screening", "getExactResult": "result", "requestPdf": "result",
	"getReport": "report", "downloadOwnPdf": "report", "getOperation": "operation",
}

// Resolve ownership in the BFF's synthetic stores. A URL or result reference
// selects a target, never its owner. A miss still gets an audited IAM denial.
func (a *API) checkResource(c *call, id string) error {
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
	case "result":
		ref := c.result()
		if id == "requestPdf" {
			var x domain.ReportRequest
			if err := json.Unmarshal(c.body, &x); err != nil || x.Kind != "screening" || x.Result == nil {
				return domain.NotFound()
			}
			ref = *x.Result
		}
		r = domain.Ref("result", ref.ID, ref.Version)
		_, lookup = a.screenings.Exact(c.actor.ID, ref)
	case "report":
		r = domain.Ref("report", c.id("report_id"))
		_, lookup = a.reports.Get(c.actor, r.ID)
	case "operation":
		r = domain.Ref("operation", c.id("operation_id"))
		_, lookup = a.commands.Get(c.actor, c.id("owner"), r.ID)
	default:
		return domain.NotFound()
	}
	owner := ""
	if lookup == nil {
		owner = c.actor.ID
	}
	if err := a.auth.Check(c.ctx, c.login, id, r, owner); err != nil {
		return err
	}
	return lookup
}
