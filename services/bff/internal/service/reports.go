package service

import (
	"time"

	"portal/bff/internal/models"
)

const reportSharePath = "/shared-report"

type ResultReader interface {
	Exact(string, models.ResultRef) (models.Result, error)
}

type ShareKey = models.ShareKey
type Reports struct {
	Runtime
	Results  ResultReader
	Records  Store[OwnedID, models.Report]
	Shares   Store[ShareKey, *models.Grant]
	Tokens   Store[string, *models.Grant]
	ShareTTL time.Duration
}

func (s Reports) AuthorizeCreate(actor *models.Actor, request models.ReportRequest) error {
	if request.Kind == models.DoctorReport {
		return actor.RequirePatient()
	}
	return nil
}

func (s Reports) Create(a *models.Actor, x models.ReportRequest) ([]models.Resource, error) {
	if err := s.AuthorizeCreate(a, x); err != nil {
		return nil, err
	}
	if x.Result != nil {
		if _, err := s.Results.Exact(a.ID, *x.Result); err != nil {
			return nil, err
		}
	}
	r := models.Report{ID: s.ID(), Status: "ready", Specification: x, Snapshot: s.Now()}
	s.Records.Put(OwnedID{Owner: a.ID, ID: r.ID}, r)
	return []models.Resource{models.Ref("report", r.ID)}, nil
}

func (s Reports) Find(owner, id string) (models.Report, error) {
	r, ok := s.Records.Get(OwnedID{Owner: owner, ID: id})
	if !ok {
		return r, models.NotFound()
	}
	return r, nil
}

func (s Reports) Get(a *models.Actor, id string) (models.Report, error) {
	r, err := s.Find(a.ID, id)
	if err != nil {
		return r, err
	}
	return r, r.Accessible(a)
}

func (s Reports) Issue(a *models.Actor, id, origin string) ([]models.Resource, error) {
	if err := a.RequirePatient(); err != nil {
		return nil, err
	}
	r, err := s.Get(a, id)
	if err != nil {
		return nil, err
	}
	if r.Specification.Kind != models.DoctorReport {
		return nil, models.Fail(models.Conflict, "DOCTOR_REPORT_REQUIRED")
	}
	issued, token := s.Now(), s.Token()
	share := models.Share{
		ID:      s.ID(),
		Report:  id,
		Issued:  issued,
		Expires: issued.Add(s.ShareTTL),
		URL:     origin + reportSharePath + "#" + token,
	}
	g := &models.Grant{Owner: a, Share: share}
	s.Shares.Put(ShareKey{Owner: a.ID, Report: id, Share: share.ID}, g)
	s.Tokens.Put(token, g)
	return []models.Resource{models.Ref("share", share.ID)}, nil
}

func (s Reports) grant(a *models.Actor, id, share string) (*models.Grant, error) {
	if err := a.RequirePatient(); err != nil {
		return nil, err
	}
	g, ok := s.Shares.Get(ShareKey{Owner: a.ID, Report: id, Share: share})
	if !ok {
		return nil, models.NotFound()
	}
	return g, nil
}

func (s Reports) Share(a *models.Actor, id, share string) (models.Share, error) {
	g, err := s.grant(a, id, share)
	if err != nil {
		return models.Share{}, err
	}
	return g.Active(s.Now())
}

func (s Reports) Revoke(a *models.Actor, id, share string) ([]models.Resource, error) {
	g, err := s.grant(a, id, share)
	if err != nil {
		return nil, err
	}
	g.Revoked = true
	return []models.Resource{models.Ref("share", share)}, nil
}

func (s Reports) Redeem(token string) (models.Share, error) {
	g, ok := s.Tokens.Get(token)
	if !ok {
		return models.Share{}, models.NotFound()
	}
	return g.Active(s.Now())
}
