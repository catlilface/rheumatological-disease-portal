package application

import (
	"time"

	"portal/bff/internal/domain"
)

type ResultReader interface {
	Exact(string, domain.ResultRef) (domain.Result, error)
}
type ShareKey struct{ Owner, Report, Share string }
type Reports struct {
	Runtime
	Results ResultReader
	Records Store[OwnedID, domain.Report]
	Shares  Store[ShareKey, *domain.Grant]
	Tokens  Store[string, *domain.Grant]
}

func (s Reports) Create(a *domain.Actor, x domain.ReportRequest) ([]domain.Resource, error) {
	if x.Kind == "doctor" {
		if err := a.RequirePatient(); err != nil {
			return nil, err
		}
	}
	if x.Result != nil {
		if _, err := s.Results.Exact(a.ID, *x.Result); err != nil {
			return nil, err
		}
	}
	r := domain.Report{ID: s.ID(), Status: "ready", Specification: x, Snapshot: s.Now()}
	s.Records.Put(OwnedID{a.ID, r.ID}, r)
	return []domain.Resource{domain.Ref("report", r.ID)}, nil
}
func (s Reports) Get(a *domain.Actor, id string) (domain.Report, error) {
	r, ok := s.Records.Get(OwnedID{a.ID, id})
	if !ok {
		return r, domain.NotFound()
	}
	return r, r.Accessible(a)
}
func (s Reports) Issue(a *domain.Actor, id, origin string) ([]domain.Resource, error) {
	if err := a.RequirePatient(); err != nil {
		return nil, err
	}
	r, err := s.Get(a, id)
	if err != nil {
		return nil, err
	}
	if r.Specification.Kind != "doctor" {
		return nil, domain.Fail(domain.Conflict, "DOCTOR_REPORT_REQUIRED")
	}
	issued, token := s.Now(), s.Token()
	share := domain.Share{ID: s.ID(), Report: id, Issued: issued, Expires: issued.Add(24 * time.Hour), URL: origin + "/shared-report#" + token}
	g := &domain.Grant{Owner: a, Share: share}
	s.Shares.Put(ShareKey{a.ID, id, share.ID}, g)
	s.Tokens.Put(token, g)
	return []domain.Resource{domain.Ref("share", share.ID)}, nil
}
func (s Reports) grant(a *domain.Actor, id, share string) (*domain.Grant, error) {
	if err := a.RequirePatient(); err != nil {
		return nil, err
	}
	g, ok := s.Shares.Get(ShareKey{a.ID, id, share})
	if !ok {
		return nil, domain.NotFound()
	}
	return g, nil
}
func (s Reports) Share(a *domain.Actor, id, share string) (domain.Share, error) {
	g, err := s.grant(a, id, share)
	if err != nil {
		return domain.Share{}, err
	}
	return g.Active(s.Now())
}
func (s Reports) Revoke(a *domain.Actor, id, share string) ([]domain.Resource, error) {
	g, err := s.grant(a, id, share)
	if err != nil {
		return nil, err
	}
	g.Revoked = true
	return []domain.Resource{domain.Ref("share", share)}, nil
}
func (s Reports) Redeem(token string) (domain.Share, error) {
	g, ok := s.Tokens.Get(token)
	if !ok {
		return domain.Share{}, domain.NotFound()
	}
	return g.Active(s.Now())
}
