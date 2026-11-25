package fixtures

import (
	"testing"

	"portal/bff/internal/domain"
)

func TestSurveyFixtureIsValid(t *testing.T) {
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	s := c.Survey
	if err := s.Validate(); err != nil {
		t.Fatal(err)
	}
	if s.Blocks[2].Questions[0].Code != "В1" || s.Scoring.Thresholds["high"][1] != nil {
		t.Fatal("lost Unicode question or open threshold")
	}
}
func TestMalformedSurveyIsRejected(t *testing.T) {
	for name, breakSurvey := range map[string]func(*domain.Survey){"unknown type": func(s *domain.Survey) { s.Blocks[0].Questions[0].Type = "unknown" }, "missing options": func(s *domain.Survey) { s.Blocks[0].Questions[1].Options = nil }, "short interval": func(s *domain.Survey) { s.Scoring.Thresholds["high"] = s.Scoring.Thresholds["high"][:1] }} {
		t.Run(name, func(t *testing.T) {
			c, err := Load()
			if err != nil {
				t.Fatal(err)
			}
			breakSurvey(&c.Survey)
			if c.Survey.Validate() == nil {
				t.Fatal("accepted malformed fixture")
			}
		})
	}
}
