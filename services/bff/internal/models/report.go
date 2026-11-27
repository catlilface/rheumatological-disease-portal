package models

import "time"

const DoctorReport = "doctor"

type ReportRequest struct {
	Kind     string     `json:"kind"`
	Result   *ResultRef `json:"result,omitempty"`
	From     string     `json:"from_date,omitempty"`
	To       string     `json:"to_date,omitempty"`
	Sections []string   `json:"sections,omitempty"`
}

func (x ReportRequest) Validate() error {
	if x.From > x.To {
		return Fail(Invalid, "VALIDATION_ERROR")
	}
	return nil
}

type Report struct {
	ID            string        `json:"report_id"`
	Status        string        `json:"status"`
	Specification ReportRequest `json:"specification"`
	Snapshot      time.Time     `json:"snapshot_at"`
}

func (r Report) Accessible(a *Actor) error {
	if r.Specification.Kind == DoctorReport {
		return a.RequirePatient()
	}
	return nil
}

type Share struct {
	ID      string    `json:"share_id"`
	Report  string    `json:"report_id"`
	Issued  time.Time `json:"issued_at"`
	Expires time.Time `json:"expires_at"`
	URL     string    `json:"url"`
}

type Grant struct {
	Owner   *Actor
	Share   Share
	Revoked bool
}

func (g Grant) Active(at time.Time) (Share, error) {
	if g.Revoked || !g.Owner.Consent || !at.Before(g.Share.Expires) {
		return Share{}, Fail(Gone, "SHARE_EXPIRED_OR_REVOKED")
	}
	return g.Share, nil
}
