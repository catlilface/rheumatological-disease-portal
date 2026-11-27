package delivery

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/twmb/franz-go/pkg/kgo"
)

const (
	Header  = "mis-delivery"
	Command = "command"
	Event   = "event"
)

var (
	ErrConflict = errors.New("delivery idempotency conflict")
	ErrRejected = errors.New("delivery handler rejected message")
	topicName   = regexp.MustCompile(`^[a-zA-Z0-9._-]{1,249}$`)
)

type Metadata struct {
	ID          uuid.UUID `json:"id"`
	OperationID uuid.UUID `json:"operation_id"`
	Stream      string    `json:"stream"`
	EntityID    uuid.UUID `json:"entity_id"`
	Version     int64     `json:"version"`
	Kind        string    `json:"kind"`
}

func (m Metadata) Key() string {
	return m.Stream + ":" + m.EntityID.String()
}

type Message struct {
	Topic    string
	Metadata Metadata
	Payload  []byte
}

func (m Message) validate() error {
	meta := m.Metadata
	if !ValidTopic(m.Topic) || m.Payload == nil {
		return errors.New("invalid delivery topic or payload")
	}
	if meta.ID == uuid.Nil || meta.OperationID == uuid.Nil || meta.EntityID == uuid.Nil ||
		meta.Version < 1 || meta.Stream == "" || !utf8.ValidString(meta.Stream) ||
		strings.ContainsRune(meta.Stream, 0) || (meta.Kind != Command && meta.Kind != Event) {
		return errors.New("invalid delivery metadata")
	}
	return nil
}

func ValidTopic(topic string) bool {
	return topicName.MatchString(topic) && topic != "." && topic != ".."
}

func (m Message) fingerprint() []byte {
	meta := m.Metadata
	meta.ID = uuid.Nil
	identity, _ := json.Marshal(struct {
		Topic    string
		Metadata Metadata
	}{m.Topic, meta})
	hash := sha256.New()
	hash.Write(identity)
	hash.Write([]byte{0})
	hash.Write(m.Payload)
	return hash.Sum(nil)
}

func decode(record *kgo.Record) (Message, error) {
	var header []byte
	found := false
	for _, item := range record.Headers {
		if item.Key != Header {
			continue
		}
		if found {
			return Message{}, errors.New("duplicate delivery header")
		}
		found, header = true, item.Value
	}
	if !found || !utf8.Valid(header) {
		return Message{}, errors.New("missing or invalid delivery header")
	}
	message := Message{Topic: record.Topic, Payload: record.Value}
	if err := json.Unmarshal(header, &message.Metadata); err != nil {
		return Message{}, fmt.Errorf("decode delivery header: %w", err)
	}
	if string(record.Key) != message.Metadata.Key() {
		return Message{}, errors.New("invalid delivery key")
	}
	return message, message.validate()
}
