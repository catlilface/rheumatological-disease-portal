package models

type Reviewed struct {
	Title    string `json:"title"`
	Version  int    `json:"version"`
	Reviewer struct {
		Name string `json:"display_name"`
	} `json:"reviewer"`
	PublishedAt string `json:"published_at"`
}

type Summary struct {
	Reviewed
	Slug    string `json:"slug"`
	Section string `json:"section"`
	Summary string `json:"summary"`
	Tag     string `json:"disease_tag,omitempty"`
}

type Source struct {
	Title string `json:"title"`
	URL   string `json:"url"`
}

type Article struct {
	Summary
	Template string   `json:"template_version"`
	Body     string   `json:"body_markdown"`
	Sources  []Source `json:"sources"`
}

type DoctorRoute struct {
	Reviewed
	Body    string   `json:"body_markdown"`
	Sources []Source `json:"sources"`
}
