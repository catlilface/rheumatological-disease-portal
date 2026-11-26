package application

import "portal/bff/internal/domain"

type OwnedID struct{ Owner, ID string }
type OwnedResult struct {
	Owner string
	domain.ResultRef
}
type Screening struct {
	Runtime
	Archive interface {
		SaveResult(string, domain.Result) error
		Result(string, domain.ResultRef) (domain.Result, error)
		History(string, domain.Window) (domain.Page[domain.Result], error)
	}
	Definition        domain.Survey
	ExplanationSource SourceRef
	Sessions          Store[OwnedID, *domain.Session]
	Results           Store[OwnedResult, domain.Result]
	Explanations      Store[OwnedResult, Explanation]
}
type Start struct {
	SurveyID   string `json:"survey_id"`
	Weights    string `json:"weights_version"`
	Disclaimer string `json:"disclaimer_version"`
	Accepted   bool   `json:"disclaimer_accepted"`
}

func (s Screening) Survey(id string, version *string) (domain.Survey, error) {
	v := s.Definition
	if id != v.SurveyID || version != nil && *version != v.WeightsVersion {
		return domain.Survey{}, domain.NotFound()
	}
	return v, nil
}

func (s Screening) Start(owner string, x Start) ([]domain.Resource, error) {
	v := s.Definition
	if !x.Accepted {
		return nil, domain.Fail(domain.Invalid, "CONFIRMATION_REQUIRED")
	}
	if x.SurveyID != v.SurveyID || x.Weights != v.WeightsVersion {
		return nil, domain.Fail(domain.Missing, "SURVEY_NOT_FOUND")
	}
	if x.Disclaimer != v.DisclaimerVersion {
		return nil, domain.Fail(domain.Invalid, "DISCLAIMER_VERSION_MISMATCH")
	}
	session := domain.StartSession(v, s.ID())
	s.Sessions.Put(OwnedID{owner, session.ID}, session)
	return []domain.Resource{domain.Ref("screening", session.ID, 1)}, nil
}
func (s Screening) Get(key OwnedID) (*domain.Session, error) {
	v, ok := s.Sessions.Get(key)
	if !ok {
		return nil, domain.NotFound()
	}
	return v, nil
}
func (s Screening) Exact(owner string, ref domain.ResultRef) (domain.Result, error) {
	if s.Archive != nil {
		return s.Archive.Result(owner, ref)
	}
	v, ok := s.Results.Get(OwnedResult{owner, ref})
	if !ok {
		return v, domain.NotFound()
	}
	return v, nil
}
func (s Screening) History(owner string, w domain.Window) (domain.Page[domain.Result], error) {
	if s.Archive == nil {
		return domain.Page[domain.Result]{}, domain.NotFound()
	}
	return s.Archive.History(owner, w)
}
func (s Screening) Latest(key OwnedID) (domain.Result, error) {
	session, err := s.Get(key)
	if err != nil {
		return domain.Result{}, err
	}
	if session.Result == nil {
		return domain.Result{}, domain.Fail(domain.Conflict, "RESULT_NOT_READY")
	}
	return s.Exact(key.Owner, *session.Result)
}

type Revision struct {
	Version int `json:"expected_session_version"`
}
type Answer struct {
	Revision
	domain.AnswerValue
}

func (s Screening) change(key OwnedID, v int, action func(*domain.Session) (bool, error)) ([]domain.Resource, error) {
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
	refs := []domain.Resource{domain.Ref("screening", session.ID, session.Version)}
	if snapshot {
		r := session.Snapshot(s.Definition, s.ID)
		if s.Archive != nil {
			if err := s.Archive.SaveResult(key.Owner, r); err != nil {
				return nil, err
			}
		} else {
			s.Results.Put(OwnedResult{key.Owner, r.ResultRef}, r)
		}
		refs = append(refs, domain.Ref("result", r.ID, r.Version))
	}
	s.Sessions.Put(key, session)
	return refs, nil
}
func (s Screening) Answer(key OwnedID, a Answer) ([]domain.Resource, error) {
	return s.change(key, a.Version, func(v *domain.Session) (bool, error) {
		err := v.Answer(s.Definition, a.AnswerValue)
		return v.HasFlags(), err
	})
}
func (s Screening) Continue(key OwnedID, x Revision) ([]domain.Resource, error) {
	return s.change(key, x.Version, func(v *domain.Session) (bool, error) { return false, v.Continue() })
}
func (s Screening) Complete(key OwnedID, x Revision) ([]domain.Resource, error) {
	return s.change(key, x.Version, func(v *domain.Session) (bool, error) { return true, v.Complete(s.Definition) })
}
func (s Screening) Abandon(key OwnedID, x Revision) ([]domain.Resource, error) {
	return s.change(key, x.Version, func(v *domain.Session) (bool, error) { v.Abandon(); return false, nil })
}

type SourceRef struct {
	Slug    string `json:"slug"`
	Version int    `json:"version"`
}
type Explanation struct {
	Result     domain.ResultRef `json:"result"`
	Mode       string           `json:"mode"`
	Text       string           `json:"explanation"`
	Questions  []string         `json:"questions_for_doctor"`
	Sources    []SourceRef      `json:"sources"`
	Disclaimer string           `json:"disclaimer"`
}

func (s Screening) Explain(owner string, ref domain.ResultRef) ([]domain.Resource, error) {
	r, err := s.Exact(owner, ref)
	if err != nil {
		return nil, err
	}
	s.Explanations.Put(OwnedResult{owner, ref}, Explanation{ref, "curated_fallback", "Демонстрационный уровень: " + r.Risk + ".", []string{"Какие из записанных симптомов стоит обсудить на приёме?"}, []SourceRef{s.ExplanationSource}, r.Disclaimer})
	return []domain.Resource{domain.Ref("result", ref.ID, ref.Version)}, nil
}
func (s Screening) Explanation(owner string, ref domain.ResultRef) (Explanation, error) {
	if _, err := s.Exact(owner, ref); err != nil {
		return Explanation{}, err
	}
	v, ok := s.Explanations.Get(OwnedResult{owner, ref})
	if !ok {
		return v, domain.Fail(domain.Missing, "EXPLANATION_NOT_READY")
	}
	return v, nil
}
