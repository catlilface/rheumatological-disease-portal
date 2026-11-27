package handler

import (
	"portal/bff/internal/models"
	"portal/bff/internal/service"
)

type patient = service.PatientCabinet

func (c *call) period() models.Period {
	return models.Period{From: c.id("from_date"), To: c.id("to_date")}
}

func cabinetCommand[T any](a *API, s service.Cabinets, id string, apply func(patient, *call, T) ([]models.Resource, error)) {
	a.on(id, member, bind(func(c *call, x T) (any, error) {
		return c.receipt(a.commands.RunCabinet(c.actor, c.id(idempotencyHeader), c.fingerprint, s, func(p patient) ([]models.Resource, error) {
			return apply(p, c, x)
		}))
	}))
}

func (a *API) Cabinet(s service.Cabinets) {
	get := func(id string, f func(patient, *call) (any, error)) {
		a.on(id, member, func(c *call) (any, error) {
			p, err := s.For(c.actor)
			if err != nil {
				return nil, err
			}
			return f(p, c)
		})
	}
	get(opGetOnboarding, func(p patient, c *call) (any, error) { return p.Onboarding(), nil })
	get(opGetReminderSettings, func(p patient, c *call) (any, error) { return p.Reminders(), nil })
	get(opListMedications, func(p patient, c *call) (any, error) { return p.Medications(c.window), nil })
	get(opListDoses, func(p patient, c *call) (any, error) {
		return p.Doses(c.period(), c.id("status"), c.id("medication_id"), c.window)
	})
	get(opListNotifications, func(p patient, c *call) (any, error) { return p.Notices(c.id("unread") == "true", c.window), nil })
	get(opListDiaryEntries, func(p patient, c *call) (any, error) { return p.Entries(c.period(), c.window) })
	get(opGetDiaryEntry, func(p patient, c *call) (any, error) { return p.Entry(c.id("entry_id")) })
	cabinetCommand(a, s, opFinishOnboarding, func(p patient, c *call, x models.OnboardingInput) ([]models.Resource, error) { return p.Finish(x) })
	cabinetCommand(a, s, opUpdateReminderSettings, func(p patient, c *call, x models.ReminderSettings) ([]models.Resource, error) {
		return nil, p.SetReminders(x)
	})
	for _, id := range []string{"addMedication", "updateMedication"} {
		cabinetCommand(a, s, id, func(p patient, c *call, x models.Regimen) ([]models.Resource, error) {
			return p.SaveMedication(c.id("medication_id"), x)
		})
	}
	cabinetCommand(a, s, opStopMedication, func(p patient, c *call, _ empty) ([]models.Resource, error) {
		return nil, p.StopMedication(c.id("medication_id"))
	})
	cabinetCommand(a, s, opMarkIntake, func(p patient, c *call, x models.Intake) ([]models.Resource, error) {
		return p.Mark(c.id("dose_id"), x)
	})
	cabinetCommand(a, s, opReadNotification, func(p patient, c *call, _ empty) ([]models.Resource, error) { return p.Read(c.id("notification_id")) })
	for _, id := range []string{"createDiaryEntry", "replaceDiaryEntry"} {
		cabinetCommand(a, s, id, func(p patient, c *call, x models.DiaryData) ([]models.Resource, error) {
			return p.SaveEntry(c.id("entry_id"), x)
		})
	}
	cabinetCommand(a, s, opDeleteDiaryEntry, func(p patient, c *call, _ empty) ([]models.Resource, error) {
		return nil, p.DeleteEntry(c.id("entry_id"))
	})
}
