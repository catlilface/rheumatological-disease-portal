package service

import "portal/bff/internal/models"

type Cabinets struct {
	Runtime
	Records Store[string, *models.Cabinet]
}

// PatientCabinet is an owner-scoped use case, valid within one unit of work.
// The transport never obtains a repository, clock, ID generator or mutable domain aggregate.
type PatientCabinet struct {
	record  *models.Cabinet
	runtime Runtime
}

func (s Cabinets) For(a *models.Actor) (PatientCabinet, error) {
	if err := a.RequirePatient(); err != nil {
		return PatientCabinet{}, err
	}
	c, ok := s.Records.Get(a.ID)
	if !ok {
		c = models.NewCabinet()
		s.Records.Put(a.ID, c)
	}
	return PatientCabinet{c, s.Runtime}, nil
}

func (p PatientCabinet) Onboarding() models.Onboarding { return p.record.Onboarding() }
func (p PatientCabinet) Finish(x models.OnboardingInput) ([]models.Resource, error) {
	return p.record.Finish(x, p.runtime.Now(), p.runtime.ID)
}

func (p PatientCabinet) Reminders() models.ReminderSettings { return p.record.Reminders() }
func (p PatientCabinet) SetReminders(x models.ReminderSettings) error {
	return p.record.SetReminders(x)
}

func (p PatientCabinet) Medications(w models.Window) models.Page[models.Medication] {
	return p.record.Medications(w)
}

func (p PatientCabinet) SaveMedication(id string, x models.Regimen) ([]models.Resource, error) {
	return p.record.SaveMedication(id, x, p.runtime.Now(), p.runtime.ID)
}

func (p PatientCabinet) StopMedication(id string) error {
	return p.record.StopMedication(id, p.runtime.Now())
}

func (p PatientCabinet) Doses(period models.Period, status, med string, w models.Window) (models.Page[models.Dose], error) {
	return p.record.Doses(period, status, med, w, p.runtime.Now())
}

func (p PatientCabinet) Mark(id string, x models.Intake) ([]models.Resource, error) {
	return p.record.Mark(id, x, p.runtime.Now())
}

func (p PatientCabinet) Entries(period models.Period, w models.Window) (models.Page[models.DiaryEntry], error) {
	return p.record.Entries(period, w)
}

func (p PatientCabinet) Entry(id string) (models.DiaryEntry, error) { return p.record.Entry(id) }
func (p PatientCabinet) SaveEntry(id string, x models.DiaryData) ([]models.Resource, error) {
	return p.record.SaveEntry(id, x, p.runtime.ID)
}

func (p PatientCabinet) DeleteEntry(id string) error { return p.record.DeleteEntry(id) }
func (p PatientCabinet) Notices(unread bool, w models.Window) models.Page[models.Notification] {
	return p.record.Notices(unread, w)
}

func (p PatientCabinet) Read(id string) ([]models.Resource, error) { return p.record.Read(id) }
