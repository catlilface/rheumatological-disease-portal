package domain

import (
	"fmt"
	"slices"
)

// Validate the scoring definition once, before exposing a revision. Overlapping or
// incomplete thresholds otherwise make risk classification depend on map iteration order.
func (s Survey) Validate() error {
	if s.SurveyID == "" || s.WeightsVersion == "" || len(s.Blocks) == 0 {
		return fmt.Errorf("empty survey definition")
	}
	questions, blocks := map[string]bool{}, map[string]bool{}
	for _, b := range s.Blocks {
		if b.Code == "" || blocks[b.Code] || len(b.Questions) == 0 {
			return fmt.Errorf("invalid block %q", b.Code)
		}
		blocks[b.Code] = true
		for _, q := range b.Questions {
			if q.Code == "" || questions[q.Code] || q.Text == "" {
				return fmt.Errorf("invalid question %q", q.Code)
			}
			questions[q.Code] = true
			switch q.Type {
			case "boolean":
				if slices.Contains(s.Scoring.SumBlocks, b.Code) {
					for _, v := range []string{"yes", "no"} {
						if _, ok := q.Weights[v]; !ok {
							return fmt.Errorf("missing %s weight for %s", v, q.Code)
						}
					}
				}
			case "single_choice":
				if len(q.Options) == 0 {
					return fmt.Errorf("no choices for %s", q.Code)
				}
			default:
				return fmt.Errorf("unknown question type %q", q.Type)
			}
		}
	}
	for _, code := range s.Scoring.SumBlocks {
		if !blocks[code] {
			return fmt.Errorf("unknown scoring block %q", code)
		}
	}
	next := 0
	for _, level := range []string{"low", "medium", "high"} {
		r := s.Scoring.Thresholds[level]
		if len(r) != 2 || r[0] == nil || *r[0] != next {
			return fmt.Errorf("invalid lower threshold for %s", level)
		}
		if level == "high" && r[1] != nil || level != "high" && r[1] == nil {
			return fmt.Errorf("invalid upper threshold for %s", level)
		}
		if r[1] != nil {
			if *r[1] < next {
				return fmt.Errorf("inverted threshold for %s", level)
			}
			next = *r[1] + 1
		}
	}
	if len(s.Scoring.Thresholds) != 3 {
		return fmt.Errorf("unexpected threshold category")
	}
	return nil
}
