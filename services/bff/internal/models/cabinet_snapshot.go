package models

import "encoding/json"

// Private persistence representation, not the HTTP projection.
type cabinetRecord struct {
	Name        string
	Completed   bool
	Diagnosis   *string
	Reminders   ReminderSettings
	Medications map[string]Medication
	Diary       map[string]DiaryEntry
	Slots       map[string]Dose
	Notices     map[string]Notification
}

func (c Cabinet) MarshalJSON() ([]byte, error) {
	return json.Marshal(cabinetRecord{c.name, c.completed, c.diagnosis, c.reminders, c.meds, c.diary, c.slots, c.notices})
}
func (c *Cabinet) UnmarshalJSON(b []byte) error {
	var r cabinetRecord
	if err := json.Unmarshal(b, &r); err != nil {
		return err
	}
	*c = Cabinet{r.Name, r.Completed, r.Diagnosis, r.Reminders, r.Medications, r.Diary, r.Slots, r.Notices}
	return nil
}
