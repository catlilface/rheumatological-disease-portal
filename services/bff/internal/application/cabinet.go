package application

import "portal/bff/internal/domain"

type Cabinets struct {
	Runtime
	Records Store[string, *domain.Cabinet]
}

// PatientCabinet is an owner-scoped application service, valid within one unit of work.
// The transport never obtains a repository, clock, ID generator or mutable domain aggregate.
type PatientCabinet struct {
	record  *domain.Cabinet
	runtime Runtime
}

func (s Cabinets) For(a *domain.Actor) (PatientCabinet, error) {
	if err := a.RequirePatient(); err != nil {
		return PatientCabinet{}, err
	}
	c, ok := s.Records.Get(a.ID)
	if !ok {
		c = domain.NewCabinet()
		s.Records.Put(a.ID, c)
	}
	return PatientCabinet{c, s.Runtime}, nil
}
func (p PatientCabinet) Onboarding() domain.Onboarding { return p.record.Onboarding() }
func (p PatientCabinet) Finish(x domain.OnboardingInput) ([]domain.Resource, error) {
	return p.record.Finish(x, p.runtime.Now(), p.runtime.ID)
}
func (p PatientCabinet) Reminders() domain.ReminderSettings { return p.record.Reminders() }
func (p PatientCabinet) SetReminders(x domain.ReminderSettings) error {
	return p.record.SetReminders(x)
}
func (p PatientCabinet) Medications(w domain.Window) domain.Page[domain.Medication] {
	return p.record.Medications(w)
}
func (p PatientCabinet) SaveMedication(id string, x domain.Regimen) ([]domain.Resource, error) {
	return p.record.SaveMedication(id, x, p.runtime.Now(), p.runtime.ID)
}
func (p PatientCabinet) StopMedication(id string) error {
	return p.record.StopMedication(id, p.runtime.Now())
}
func (p PatientCabinet) Doses(period domain.Period, status, med string, w domain.Window) (domain.Page[domain.Dose], error) {
	return p.record.Doses(period, status, med, w, p.runtime.Now())
}
func (p PatientCabinet) Mark(id string, x domain.Intake) ([]domain.Resource, error) {
	return p.record.Mark(id, x, p.runtime.Now())
}
func (p PatientCabinet) Entries(period domain.Period, w domain.Window) (domain.Page[domain.DiaryEntry], error) {
	return p.record.Entries(period, w)
}
func (p PatientCabinet) Entry(id string) (domain.DiaryEntry, error) { return p.record.Entry(id) }
func (p PatientCabinet) SaveEntry(id string, x domain.DiaryData) ([]domain.Resource, error) {
	return p.record.SaveEntry(id, x, p.runtime.ID)
}
func (p PatientCabinet) DeleteEntry(id string) error { return p.record.DeleteEntry(id) }
func (p PatientCabinet) Notices(unread bool, w domain.Window) domain.Page[domain.Notification] {
	return p.record.Notices(unread, w)
}
func (p PatientCabinet) Read(id string) ([]domain.Resource, error) { return p.record.Read(id) }
