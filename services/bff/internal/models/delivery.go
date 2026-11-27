package models

type CounterView struct {
	Value     *int64 `json:"value"`
	Projected *int64 `json:"projected"`
}
