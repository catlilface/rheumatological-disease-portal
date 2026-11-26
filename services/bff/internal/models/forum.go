package models

import (
	"slices"
	"time"
)

const (
	demoAlias      = "Демо-участник"
	demoTopicTitle = "Добро пожаловать"
	demoTopicText  = "Тестовая тема. Не публикуйте личные медицинские данные."
	targetTopic    = "topic"
	targetPost     = "post"
	caseSubmission = "submission"
	caseComplaint  = "complaint"
)

type Message struct {
	TopicID string    `json:"topic_id"`
	PostID  string    `json:"post_id,omitempty"`
	Title   string    `json:"title,omitempty"`
	Body    string    `json:"body"`
	Alias   string    `json:"author_alias"`
	Created time.Time `json:"created_at"`
}

type Target struct {
	Kind string `json:"kind"`
	ID   string `json:"id"`
}

func (m Message) Target() Target {
	if m.PostID != "" {
		return Target{Kind: targetPost, ID: m.PostID}
	}
	return Target{Kind: targetTopic, ID: m.TopicID}
}

type Case struct {
	ID      string `json:"case_id"`
	Target  Target `json:"target"`
	Kind    string `json:"kind"`
	Body    string `json:"body"`
	Title   string `json:"title,omitempty"`
	Reason  string `json:"reason,omitempty"`
	Version int    `json:"version"`
	item    Message
}

type Decision struct {
	Action  string `json:"action"`
	Reason  string `json:"reason"`
	Version int    `json:"expected_version"`
}

// Publication order is distinct from submission order.
type Forum struct {
	topics, posts []Message
	cases         []Case
}

func NewForum(id string, t time.Time) *Forum {
	welcome := Message{
		TopicID: id,
		Alias:   demoAlias,
		Title:   demoTopicTitle,
		Body:    demoTopicText,
		Created: t,
	}
	return &Forum{topics: []Message{welcome}}
}

func (f Forum) Topics(w Window) Page[Message] {
	rows := slices.Clone(f.topics)
	slices.Reverse(rows)
	return Paginate(rows, w)
}

func (f Forum) Topic(id string) (Message, error) {
	for _, m := range f.topics {
		if m.TopicID == id {
			return m, nil
		}
	}
	return Message{}, NotFound()
}

func (f Forum) Posts(id string, w Window) (Page[Message], error) {
	if _, err := f.Topic(id); err != nil {
		return Page[Message]{}, err
	}
	var rows []Message
	for _, m := range f.posts {
		if m.TopicID == id {
			rows = append(rows, m)
		}
	}
	return Paginate(rows, w), nil
}

func (f Forum) Cases(w Window) Page[Case] { return Paginate(f.cases, w) }
func (f *Forum) open(m Message, id, reason string) []Resource {
	kind := caseSubmission
	if reason != "" {
		kind = caseComplaint
	}
	c := Case{
		ID:      id,
		Target:  m.Target(),
		Kind:    kind,
		Body:    m.Body,
		Title:   m.Title,
		Reason:  reason,
		Version: initialVersion,
		item:    m,
	}
	f.cases = append(f.cases, c)
	return []Resource{Ref(c.Target.Kind, c.Target.ID), Ref("case", id, c.Version)}
}

func (f *Forum) Submit(topic, title, body string, now time.Time, id func() string) ([]Resource, error) {
	m := Message{Title: title, Body: body, Alias: demoAlias, Created: now}
	if topic != "" {
		if _, err := f.Topic(topic); err != nil {
			return nil, err
		}
		m.PostID = id()
		m.TopicID = topic
	} else {
		m.TopicID = id()
	}
	return f.open(m, id(), ""), nil
}

func (f *Forum) Flag(target Target, reason, id string) ([]Resource, error) {
	if target.Kind == targetTopic {
		m, err := f.Topic(target.ID)
		if err != nil {
			return nil, err
		}
		return f.open(m, id, reason), nil
	}
	for _, m := range f.posts {
		if m.PostID == target.ID {
			if _, err := f.Topic(m.TopicID); err != nil {
				return nil, err
			}
			return f.open(m, id, reason), nil
		}
	}
	return nil, NotFound()
}

func (f *Forum) Decide(id string, x Decision) ([]Resource, error) {
	i := slices.IndexFunc(f.cases, func(c Case) bool { return c.ID == id })
	if i < 0 {
		return nil, NotFound()
	}
	c := f.cases[i]
	if c.Version != x.Version {
		return nil, Fail(Conflict, "CASE_VERSION_CONFLICT")
	}
	table := &f.topics
	if c.Target.Kind == targetPost {
		table = &f.posts
	}
	switch {
	case c.Kind == caseSubmission && x.Action == "approve":
		if c.Target.Kind == targetPost {
			if _, err := f.Topic(c.item.TopicID); err != nil {
				return nil, err
			}
		}
		*table = append(*table, c.item)
	case c.Kind == caseComplaint && x.Action == "hide":
		*table = slices.DeleteFunc(*table, func(m Message) bool { return m.Target() == c.Target })
	case c.Kind == caseSubmission && x.Action == "reject", c.Kind == caseComplaint && x.Action == "dismiss":
	default:
		return nil, Fail(Conflict, "INVALID_MODERATION_ACTION")
	}
	f.cases = slices.Delete(f.cases, i, i+1)
	return []Resource{Ref(c.Target.Kind, c.Target.ID)}, nil
}
