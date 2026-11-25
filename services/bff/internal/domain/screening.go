package domain

import "slices"

type SurveyMeta struct {
	SurveyID          string `json:"survey_id"`
	WeightsVersion    string `json:"weights_version"`
	DisclaimerVersion string `json:"disclaimer_version"`
	Disclaimer        string `json:"disclaimer"`
}
type Survey struct {
	SurveyMeta
	ThresholdsStatus string  `json:"thresholds_status"`
	Confirmation     string  `json:"confirmation_text"`
	UrgentNotice     string  `json:"urgent_notice"`
	Blocks           []Block `json:"blocks"`
	Scoring          struct {
		SumBlocks        []string          `json:"sum_blocks"`
		Thresholds       map[string][]*int `json:"thresholds"`
		RedFlagOverrides bool              `json:"red_flag_overrides"`
	} `json:"scoring"`
}
type Block struct {
	Code      string     `json:"code"`
	Title     string     `json:"title"`
	RedFlag   bool       `json:"red_flag"`
	Interrupt bool       `json:"interrupt"`
	Questions []Question `json:"questions"`
}
type Question struct {
	Code     string         `json:"code"`
	Text     string         `json:"text"`
	Type     string         `json:"type"`
	Required bool           `json:"required"`
	RedFlag  bool           `json:"red_flag"`
	Weights  map[string]int `json:"weights,omitempty"`
	Options  []struct {
		Value  string `json:"value"`
		Label  string `json:"label"`
		Weight int    `json:"weight"`
	} `json:"options,omitempty"`
}

func (s Survey) question(code string) (Block, Question, bool) {
	for _, b := range s.Blocks {
		for _, q := range b.Questions {
			if q.Code == code {
				return b, q, true
			}
		}
	}
	return Block{}, Question{}, false
}
func (q Question) Weight(v any) (int, bool) {
	switch x := v.(type) {
	case bool:
		if q.Type == "boolean" {
			if x {
				return q.Weights["yes"], true
			}
			return q.Weights["no"], true
		}
	case string:
		for _, o := range q.Options {
			if o.Value == x {
				return o.Weight, true
			}
		}
	}
	return 0, false
}

type AnswerValue struct {
	Code  string `json:"question_code"`
	Value any    `json:"value"`
}
type ResultRef struct {
	ID      string `json:"result_id"`
	Version int    `json:"version"`
}
type Session struct {
	SurveyMeta
	ID          string        `json:"screening_id"`
	Version     int           `json:"version"`
	Status      string        `json:"status"`
	Interrupted bool          `json:"interrupted_by_red_flag"`
	Answers     []AnswerValue `json:"answers"`
	Result      *ResultRef    `json:"result"`
	flags       []string
}

func StartSession(s Survey, id string) *Session {
	return &Session{SurveyMeta: s.SurveyMeta, ID: id, Version: 1, Status: "in_progress", Answers: []AnswerValue{}}
}
func (s Session) Editable(version int) error {
	if s.Version != version {
		return Fail(Conflict, "SESSION_VERSION_CONFLICT")
	}
	if s.Status != "in_progress" {
		return Fail(Conflict, "SESSION_CLOSED")
	}
	return nil
}
func (s *Session) Answer(survey Survey, a AnswerValue) error {
	if s.Interrupted {
		return Fail(Conflict, "CONTINUATION_REQUIRED")
	}
	_, q, ok := survey.question(a.Code)
	if !ok {
		return NotFound()
	}
	if _, ok = q.Weight(a.Value); !ok {
		return Fail(Invalid, "INVALID_ANSWER")
	}
	s.Answers = append(slices.DeleteFunc(s.Answers, func(old AnswerValue) bool { return old.Code == a.Code }), a)
	s.Version++
	if q.RedFlag && a.Value == true && !slices.Contains(s.flags, q.Code) {
		s.flags = append(s.flags, q.Code)
		slices.Sort(s.flags)
		s.Interrupted = true
	}
	return nil
}
func (s Session) CompleteAnswers(survey Survey) bool {
	for _, b := range survey.Blocks {
		for _, q := range b.Questions {
			if q.Required && !slices.ContainsFunc(s.Answers, func(a AnswerValue) bool { return a.Code == q.Code }) {
				return false
			}
		}
	}
	return true
}
func (s *Session) Continue() error {
	if !s.Interrupted {
		return Fail(Conflict, "NOT_INTERRUPTED")
	}
	s.Interrupted = false
	s.Version++
	return nil
}
func (s *Session) Complete(survey Survey) error {
	if !s.CompleteAnswers(survey) {
		return Fail(Conflict, "REQUIRED_ANSWERS_MISSING")
	}
	s.Status = "completed"
	s.Interrupted = false
	s.Version++
	return nil
}
func (s *Session) Abandon()      { s.Interrupted = false; s.Status = "abandoned"; s.Version++ }
func (s Session) HasFlags() bool { return len(s.flags) > 0 }

type Contribution struct {
	AnswerValue
	Block  string `json:"block_code"`
	Label  string `json:"label"`
	Weight int    `json:"weighted_score"`
}
type Recommendation struct {
	Code string `json:"code"`
	Text string `json:"text"`
}
type Result struct {
	SurveyMeta
	ResultRef
	ScreeningID      string           `json:"screening_id"`
	ThresholdsStatus string           `json:"thresholds_status"`
	Risk             string           `json:"risk_level"`
	RedFlag          bool             `json:"red_flag"`
	Flags            []string         `json:"red_flag_codes"`
	Score            *int             `json:"score"`
	Complete         bool             `json:"scoring_complete"`
	Blocks           map[string]int   `json:"block_scores"`
	Contributions    []Contribution   `json:"contributing_answers"`
	Recommendations  []Recommendation `json:"recommendations"`
}

func (s *Session) Snapshot(survey Survey, newID func() string) Result {
	var ref ResultRef
	if s.Result == nil {
		ref = ResultRef{newID(), 1}
	} else {
		ref = *s.Result
		ref.Version++
	}
	r := Result{SurveyMeta: s.SurveyMeta, ResultRef: ref, ScreeningID: s.ID, ThresholdsStatus: survey.ThresholdsStatus, Flags: append([]string{}, s.flags...), RedFlag: s.HasFlags(), Blocks: map[string]int{}, Contributions: []Contribution{}, Complete: s.CompleteAnswers(survey)}
	total := 0
	for _, a := range s.Answers {
		b, q, _ := survey.question(a.Code)
		if !slices.Contains(survey.Scoring.SumBlocks, b.Code) {
			continue
		}
		w, _ := q.Weight(a.Value)
		total += w
		r.Blocks[b.Code] += w
		if w != 0 {
			r.Contributions = append(r.Contributions, Contribution{a, b.Code, q.Text, w})
		}
	}
	if r.Complete {
		r.Score = &total
	}
	notice := survey.UrgentNotice
	if r.RedFlag {
		r.Risk = "red_flag"
	} else {
		for level, bounds := range survey.Scoring.Thresholds {
			if total >= *bounds[0] && (bounds[1] == nil || total <= *bounds[1]) {
				r.Risk = level
				break
			}
		}
		notice = "Тестовая рекомендация для категории " + r.Risk + "."
	}
	r.Recommendations = []Recommendation{{"demo_" + r.Risk, notice}}
	s.Result = &ref
	return r
}
