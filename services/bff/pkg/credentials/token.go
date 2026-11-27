package credentials

import (
	"crypto/rand"
	"encoding/base64"
)

const tokenBytes = 32

func NewToken() string {
	var token [tokenBytes]byte
	rand.Read(token[:])
	return base64.RawURLEncoding.EncodeToString(token[:])
}
