package credentials

import (
	"crypto/rand"
	"crypto/subtle"

	"golang.org/x/crypto/scrypt"
)

type Scrypt struct{}

func (Scrypt) Hash(password string) ([]byte, error) {
	salt := make([]byte, 16)
	rand.Read(salt)
	digest, err := scrypt.Key([]byte(password), salt, 16384, 8, 1, 64)
	return append(salt, digest...), err
}
func (Scrypt) Matches(hash []byte, password string) bool {
	if len(hash) != 80 {
		return false
	}
	digest, err := scrypt.Key([]byte(password), hash[:16], 16384, 8, 1, 64)
	return err == nil && subtle.ConstantTimeCompare(digest, hash[16:]) == 1
}
