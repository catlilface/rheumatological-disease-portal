package models

type OwnedID struct{ Owner, ID string }

type OwnedResult struct {
	Owner string
	ResultRef
}

type Start struct {
	SurveyID   string `json:"survey_id"`
	Weights    string `json:"weights_version"`
	Disclaimer string `json:"disclaimer_version"`
	Accepted   bool   `json:"disclaimer_accepted"`
}

type Revision struct {
	Version int `json:"expected_session_version"`
}

type Answer struct {
	Revision
	AnswerValue
}

type SourceRef struct {
	Slug    string `json:"slug"`
	Version int    `json:"version"`
}

type Explanation struct {
	Result     ResultRef   `json:"result"`
	Mode       string      `json:"mode"`
	Text       string      `json:"explanation"`
	Questions  []string    `json:"questions_for_doctor"`
	Sources    []SourceRef `json:"sources"`
	Disclaimer string      `json:"disclaimer"`
}
