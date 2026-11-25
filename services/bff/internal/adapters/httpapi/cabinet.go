package httpapi

import (
	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

type patient = application.PatientCabinet

func (c *call) period() domain.Period {
	return domain.Period{From: c.id("from_date"), To: c.id("to_date")}
}
func cabinetCommand[T any](a *API, s application.Cabinets, id string, apply func(patient, *call, T) ([]domain.Resource, error)) {
	command(a, id, member, "cabinet", func(c *call, x T) ([]domain.Resource, error) {
		p, err := s.For(c.actor)
		if err != nil {
			return nil, err
		}
		return apply(p, c, x)
	})
}
func (a *API) Cabinet(s application.Cabinets) {
	get := func(id string, f func(patient, *call) (any, error)) {
		a.on(id, member, func(c *call) (any, error) {
			p, err := s.For(c.actor)
			if err != nil {
				return nil, err
			}
			return f(p, c)
		})
	}
	get("getOnboarding", func(p patient, c *call) (any, error) { return p.Onboarding(), nil })
	get("getReminderSettings", func(p patient, c *call) (any, error) { return p.Reminders(), nil })
	get("listMedications", func(p patient, c *call) (any, error) { return p.Medications(c.window), nil })
	get("listDoses", func(p patient, c *call) (any, error) {
		return p.Doses(c.period(), c.id("status"), c.id("medication_id"), c.window)
	})
	get("listNotifications", func(p patient, c *call) (any, error) { return p.Notices(c.id("unread") == "true", c.window), nil })
	get("listDiaryEntries", func(p patient, c *call) (any, error) { return p.Entries(c.period(), c.window) })
	get("getDiaryEntry", func(p patient, c *call) (any, error) { return p.Entry(c.id("entry_id")) })
	cabinetCommand(a, s, "finishOnboarding", func(p patient, c *call, x domain.OnboardingInput) ([]domain.Resource, error) { return p.Finish(x) })
	cabinetCommand(a, s, "updateReminderSettings", func(p patient, c *call, x domain.ReminderSettings) ([]domain.Resource, error) {
		return nil, p.SetReminders(x)
	})
	for _, id := range []string{"addMedication", "updateMedication"} {
		cabinetCommand(a, s, id, func(p patient, c *call, x domain.Regimen) ([]domain.Resource, error) {
			return p.SaveMedication(c.id("medication_id"), x)
		})
	}
	cabinetCommand(a, s, "stopMedication", func(p patient, c *call, _ empty) ([]domain.Resource, error) {
		return nil, p.StopMedication(c.id("medication_id"))
	})
	cabinetCommand(a, s, "markIntake", func(p patient, c *call, x domain.Intake) ([]domain.Resource, error) {
		return p.Mark(c.id("dose_id"), x)
	})
	cabinetCommand(a, s, "readNotification", func(p patient, c *call, _ empty) ([]domain.Resource, error) { return p.Read(c.id("notification_id")) })
	for _, id := range []string{"createDiaryEntry", "replaceDiaryEntry"} {
		cabinetCommand(a, s, id, func(p patient, c *call, x domain.DiaryData) ([]domain.Resource, error) {
			return p.SaveEntry(c.id("entry_id"), x)
		})
	}
	cabinetCommand(a, s, "deleteDiaryEntry", func(p patient, c *call, _ empty) ([]domain.Resource, error) {
		return nil, p.DeleteEntry(c.id("entry_id"))
	})
}
