package service

import "portal/bff/internal/models"

type OwnedID = models.OwnedID
type OwnedResult = models.OwnedResult

type Screening struct {
	Runtime
	Archive interface {
		SaveResult(string, models.Result) error
		Result(string, models.ResultRef) (models.Result, error)
		History(string, models.Window) (models.Page[models.Result], error)
	}
	Definition        models.Survey
	ExplanationSource SourceRef
	Sessions          Store[OwnedID, *models.Session]
	Results           Store[OwnedResult, models.Result]
	Explanations      Store[OwnedResult, Explanation]
}

type Start = models.Start

func (s Screening) Survey(id string, version *string) (models.Survey, error) {
	v := s.Definition
	if id != v.SurveyID || version != nil && *version != v.WeightsVersion {
		return models.Survey{}, models.NotFound()
	}
	return v, nil
}

func (s Screening) Start(owner string, x Start) ([]models.Resource, error) {
	v := s.Definition
	if !x.Accepted {
		return nil, models.Fail(models.Invalid, "CONFIRMATION_REQUIRED")
	}
	if x.SurveyID != v.SurveyID || x.Weights != v.WeightsVersion {
		return nil, models.Fail(models.Missing, "SURVEY_NOT_FOUND")
	}
	if x.Disclaimer != v.DisclaimerVersion {
		return nil, models.Fail(models.Invalid, "DISCLAIMER_VERSION_MISMATCH")
	}
	session := models.StartSession(v, s.ID())
	s.Sessions.Put(OwnedID{Owner: owner, ID: session.ID}, session)
	return []models.Resource{models.Ref("screening", session.ID, session.Version)}, nil
}

func (s Screening) Get(key OwnedID) (*models.Session, error) {
	v, ok := s.Sessions.Get(key)
	if !ok {
		return nil, models.NotFound()
	}
	return v, nil
}

func (s Screening) Exact(owner string, ref models.ResultRef) (models.Result, error) {
	if s.Archive != nil {
		return s.Archive.Result(owner, ref)
	}
	v, ok := s.Results.Get(OwnedResult{Owner: owner, ResultRef: ref})
	if !ok {
		return v, models.NotFound()
	}
	return v, nil
}

func (s Screening) History(owner string, w models.Window) (models.Page[models.Result], error) {
	if s.Archive == nil {
		return models.Page[models.Result]{}, models.NotFound()
	}
	return s.Archive.History(owner, w)
}

func (s Screening) Latest(key OwnedID) (models.Result, error) {
	session, err := s.Get(key)
	if err != nil {
		return models.Result{}, err
	}
	if session.Result == nil {
		return models.Result{}, models.Fail(models.Conflict, "RESULT_NOT_READY")
	}
	return s.Exact(key.Owner, *session.Result)
}

type Revision = models.Revision

type Answer = models.Answer

func (s Screening) change(key OwnedID, v int, action func(*models.Session) (bool, error)) ([]models.Resource, error) {
	session, err := s.Get(key)
	if err != nil {
		return nil, err
	}
	if err = session.Editable(v); err != nil {
		return nil, err
	}
	session = session.Copy()
	snapshot, err := action(session)
	if err != nil {
		return nil, err
	}
	refs := []models.Resource{models.Ref("screening", session.ID, session.Version)}
	if snapshot {
		r := session.Snapshot(s.Definition, s.ID)
		if s.Archive != nil {
			if err := s.Archive.SaveResult(key.Owner, r); err != nil {
				return nil, err
			}
		} else {
			s.Results.Put(OwnedResult{Owner: key.Owner, ResultRef: r.ResultRef}, r)
		}
		refs = append(refs, models.Ref("result", r.ID, r.Version))
	}
	s.Sessions.Put(key, session)
	return refs, nil
}

func (s Screening) Answer(key OwnedID, a Answer) ([]models.Resource, error) {
	return s.change(key, a.Version, func(v *models.Session) (bool, error) {
		err := v.Answer(s.Definition, a.AnswerValue)
		return v.HasFlags(), err
	})
}

func (s Screening) Continue(key OwnedID, x Revision) ([]models.Resource, error) {
	return s.change(key, x.Version, func(v *models.Session) (bool, error) { return false, v.Continue() })
}

func (s Screening) Complete(key OwnedID, x Revision) ([]models.Resource, error) {
	return s.change(key, x.Version, func(v *models.Session) (bool, error) { return true, v.Complete(s.Definition) })
}

func (s Screening) Abandon(key OwnedID, x Revision) ([]models.Resource, error) {
	return s.change(key, x.Version, func(v *models.Session) (bool, error) {
		v.Abandon()
		return false, nil
	})
}

type SourceRef = models.SourceRef

type Explanation = models.Explanation

func (s Screening) Explain(owner string, ref models.ResultRef) ([]models.Resource, error) {
	r, err := s.Exact(owner, ref)
	if err != nil {
		return nil, err
	}
	explanation := Explanation{
		Result:     ref,
		Mode:       "curated_fallback",
		Text:       "Демонстрационный уровень: " + r.Risk + ".",
		Questions:  []string{"Какие из записанных симптомов стоит обсудить на приёме?"},
		Sources:    []SourceRef{s.ExplanationSource},
		Disclaimer: r.Disclaimer,
	}
	s.Explanations.Put(OwnedResult{Owner: owner, ResultRef: ref}, explanation)
	return []models.Resource{models.Ref("result", ref.ID, ref.Version)}, nil
}

func (s Screening) Explanation(owner string, ref models.ResultRef) (Explanation, error) {
	if _, err := s.Exact(owner, ref); err != nil {
		return Explanation{}, err
	}
	v, ok := s.Explanations.Get(OwnedResult{Owner: owner, ResultRef: ref})
	if !ok {
		return v, models.Fail(models.Missing, "EXPLANATION_NOT_READY")
	}
	return v, nil
}
