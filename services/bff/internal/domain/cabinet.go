package domain

import (
	"cmp"
	"slices"
	"time"
	_ "time/tzdata"
)

type ReminderSettings struct {
	Enabled  bool     `json:"enabled"`
	Timezone string   `json:"timezone"`
	Channels []string `json:"channels"`
}

func (x ReminderSettings) Validate() error {
	if _, err := time.LoadLocation(x.Timezone); err != nil || x.Timezone == "" || x.Timezone == "Local" || x.Enabled && len(x.Channels) == 0 {
		return Fail(Invalid, "VALIDATION_ERROR")
	}
	return nil
}

type Regimen struct {
	Name   string   `json:"name"`
	Dose   string   `json:"dose_text"`
	Times  []string `json:"local_times"`
	Starts string   `json:"starts_on"`
	Ends   string   `json:"ends_on,omitempty"`
}

func (x Regimen) Validate() error {
	if x.Ends != "" && x.Ends < x.Starts {
		return Fail(Invalid, "VALIDATION_ERROR")
	}
	return nil
}

type Medication struct {
	ID      string  `json:"medication_id"`
	Regimen Regimen `json:"regimen"`
}
type Dose struct {
	ID         string     `json:"dose_id"`
	Medication string     `json:"medication_id"`
	Scheduled  time.Time  `json:"scheduled_at"`
	Status     string     `json:"status"`
	Marked     *time.Time `json:"marked_at,omitempty"`
	Note       *string    `json:"note,omitempty"`
}
type Intake struct {
	Status string  `json:"status"`
	Note   *string `json:"note,omitempty"`
}
type Notification struct {
	ID      string    `json:"notification_id"`
	Channel string    `json:"channel"`
	Text    string    `json:"text"`
	Created time.Time `json:"created_at"`
	Read    bool      `json:"read"`
	Dose    string    `json:"dose_id"`
}
type DiaryData struct {
	Date      string  `json:"entry_date"`
	Pain      int     `json:"pain_vas"`
	Stiffness int     `json:"stiffness_minutes"`
	Swollen   int     `json:"swollen_joint_count"`
	Tender    int     `json:"tender_joint_count"`
	Fatigue   int     `json:"fatigue"`
	Flare     bool    `json:"flare"`
	Notes     *string `json:"notes,omitempty"`
}
type DiaryEntry struct {
	ID   string    `json:"entry_id"`
	Data DiaryData `json:"data"`
}
type OnboardingInput struct {
	Diagnosis *string          `json:"diagnosis"`
	Meds      []Regimen        `json:"medications"`
	Reminders ReminderSettings `json:"reminders"`
}

func (x OnboardingInput) Validate() error {
	for _, r := range x.Meds {
		if err := r.Validate(); err != nil {
			return err
		}
	}
	return x.Reminders.Validate()
}

type Onboarding struct {
	Completed   bool             `json:"completed"`
	Diagnosis   *string          `json:"diagnosis"`
	Medications []Medication     `json:"medications"`
	Reminders   ReminderSettings `json:"reminders"`
}
type Cabinet struct {
	completed bool
	diagnosis *string
	reminders ReminderSettings
	meds      map[string]Medication
	diary     map[string]DiaryEntry
	slots     map[string]Dose
	notices   map[string]Notification
}

func NewCabinet() *Cabinet {
	return &Cabinet{reminders: ReminderSettings{Timezone: "UTC", Channels: []string{}}, meds: map[string]Medication{}, diary: map[string]DiaryEntry{}, slots: map[string]Dose{}, notices: map[string]Notification{}}
}
func (c Cabinet) location() *time.Location {
	tz, _ := time.LoadLocation(c.reminders.Timezone)
	return tz
}
func (c Cabinet) Reminders() ReminderSettings { return c.reminders }
func (c *Cabinet) SetReminders(x ReminderSettings) error {
	if err := x.Validate(); err != nil {
		return err
	}
	c.reminders = x
	return nil
}
func (c Cabinet) medications() []Medication {
	rows := []Medication{}
	for _, v := range c.meds {
		rows = append(rows, v)
	}
	return rows
}
func (c Cabinet) Onboarding() Onboarding {
	rows := c.medications()
	slices.SortFunc(rows, func(a, b Medication) int { return cmp.Compare(a.ID, b.ID) })
	return Onboarding{c.completed, c.diagnosis, rows, c.reminders}
}
func (c *Cabinet) Finish(x OnboardingInput, now time.Time, id func() string) ([]Resource, error) {
	if c.completed {
		return nil, Fail(Conflict, "ONBOARDING_COMPLETED")
	}
	if err := x.Validate(); err != nil {
		return nil, err
	}
	c.completed, c.diagnosis, c.reminders = true, x.Diagnosis, x.Reminders
	var refs []Resource
	for _, r := range x.Meds {
		refs = append(refs, c.add(r, now, id))
	}
	return refs, nil
}
func (c *Cabinet) add(r Regimen, now time.Time, id func() string) Resource {
	m := Medication{id(), r}
	c.meds[m.ID] = m
	c.sampleSlots(m, now, id)
	return Ref("medication", m.ID)
}
func (c *Cabinet) sampleSlots(m Medication, now time.Time, id func() string) {
	r, tz := m.Regimen, c.location()
	day := max(r.Starts, now.In(tz).Format(time.DateOnly))
	if r.Ends != "" {
		day = min(day, r.Ends)
	}
	seen := map[time.Time]bool{}
	for _, d := range c.slots {
		if d.Medication == m.ID {
			seen[d.Scheduled] = true
		}
	}
	for _, local := range r.Times {
		t, _ := time.ParseInLocation("2006-01-02 15:04", day+" "+local, tz)
		t = t.UTC()
		if seen[t] {
			continue
		}
		slot := Dose{ID: id(), Medication: m.ID, Scheduled: t, Status: "scheduled"}
		c.slots[slot.ID] = slot
		seen[t] = true
		if c.reminders.Enabled {
			n := Notification{ID: id(), Channel: "in_app", Text: "Демонстрационное напоминание", Created: now, Dose: slot.ID}
			c.notices[n.ID] = n
		}
	}
}
func (c *Cabinet) removeFuture(m string, now time.Time) {
	for id, d := range c.slots {
		if d.Medication == m && d.Status == "scheduled" && d.Scheduled.After(now) {
			delete(c.slots, id)
		}
	}
	for id, n := range c.notices {
		if _, ok := c.slots[n.Dose]; !ok {
			delete(c.notices, id)
		}
	}
}
func (c *Cabinet) SaveMedication(key string, r Regimen, now time.Time, id func() string) ([]Resource, error) {
	if err := r.Validate(); err != nil {
		return nil, err
	}
	if key == "" {
		return []Resource{c.add(r, now, id)}, nil
	}
	if _, ok := c.meds[key]; !ok {
		return nil, NotFound()
	}
	c.removeFuture(key, now)
	m := Medication{key, r}
	c.meds[key] = m
	c.sampleSlots(m, now, id)
	return []Resource{Ref("medication", key)}, nil
}
func (c *Cabinet) StopMedication(key string, now time.Time) error {
	m, ok := c.meds[key]
	if !ok {
		return NotFound()
	}
	c.removeFuture(key, now)
	for _, d := range c.slots {
		if d.Medication == key {
			today := now.In(c.location()).Format(time.DateOnly)
			if m.Regimen.Ends != "" {
				today = min(today, m.Regimen.Ends)
			}
			m.Regimen.Ends = max(m.Regimen.Starts, today)
			c.meds[key] = m
			return nil
		}
	}
	delete(c.meds, key)
	return nil
}
func (c Cabinet) Medications(w Window) Page[Medication] {
	rows := c.medications()
	slices.SortFunc(rows, func(a, b Medication) int {
		return cmp.Or(cmp.Compare(a.Regimen.Name, b.Regimen.Name), cmp.Compare(a.ID, b.ID))
	})
	return Paginate(rows, w)
}

type Period struct{ From, To string }

func (p Period) Valid() bool { return p.From == "" || p.To == "" || p.To >= p.From }
func (p Period) Contains(day string) bool {
	return (p.From == "" || day >= p.From) && (p.To == "" || day <= p.To)
}
func (c Cabinet) Doses(p Period, status, med string, w Window, now time.Time) (Page[Dose], error) {
	if !p.Valid() || (p.From == "") != (p.To == "") {
		return Page[Dose]{}, Fail(Invalid, "INVALID_DATE_RANGE")
	}
	tz := c.location()
	if p.From == "" {
		p.From = now.In(tz).Format(time.DateOnly)
		p.To = p.From
	}
	var rows []Dose
	for _, d := range c.slots {
		if (med == "" || d.Medication == med) && (status == "" || d.Status == status) && p.Contains(d.Scheduled.In(tz).Format(time.DateOnly)) {
			rows = append(rows, d)
		}
	}
	slices.SortFunc(rows, func(a, b Dose) int { return cmp.Or(b.Scheduled.Compare(a.Scheduled), cmp.Compare(a.ID, b.ID)) })
	return Paginate(rows, w), nil
}
func (c *Cabinet) Mark(key string, x Intake, now time.Time) ([]Resource, error) {
	d, ok := c.slots[key]
	if !ok {
		return nil, NotFound()
	}
	d.Status, d.Note, d.Marked = x.Status, x.Note, &now
	c.slots[key] = d
	return []Resource{Ref("dose", key)}, nil
}
func (c Cabinet) Notices(unread bool, w Window) Page[Notification] {
	var rows []Notification
	for _, n := range c.notices {
		if !unread || !n.Read {
			rows = append(rows, n)
		}
	}
	slices.SortFunc(rows, func(a, b Notification) int { return cmp.Compare(b.ID, a.ID) })
	return Paginate(rows, w)
}
func (c *Cabinet) Read(key string) ([]Resource, error) {
	n, ok := c.notices[key]
	if !ok {
		return nil, NotFound()
	}
	n.Read = true
	c.notices[key] = n
	return []Resource{Ref("notification", key)}, nil
}
func (c Cabinet) Entry(id string) (DiaryEntry, error) {
	e, ok := c.diary[id]
	if !ok {
		return e, NotFound()
	}
	return e, nil
}
func (c *Cabinet) SaveEntry(key string, x DiaryData, id func() string) ([]Resource, error) {
	if key == "" {
		key = id()
	} else if _, err := c.Entry(key); err != nil {
		return nil, err
	}
	c.diary[key] = DiaryEntry{key, x}
	return []Resource{Ref("diary_entry", key)}, nil
}
func (c *Cabinet) DeleteEntry(key string) error {
	if _, err := c.Entry(key); err != nil {
		return err
	}
	delete(c.diary, key)
	return nil
}
func (c Cabinet) Entries(p Period, w Window) (Page[DiaryEntry], error) {
	if !p.Valid() {
		return Page[DiaryEntry]{}, Fail(Invalid, "INVALID_DATE_RANGE")
	}
	var rows []DiaryEntry
	for _, e := range c.diary {
		if p.Contains(e.Data.Date) {
			rows = append(rows, e)
		}
	}
	slices.SortFunc(rows, func(a, b DiaryEntry) int {
		return cmp.Or(cmp.Compare(b.Data.Date, a.Data.Date), cmp.Compare(b.ID, a.ID))
	})
	return Paginate(rows, w), nil
}
