package credentials

import (
	"crypto/rand"
	"crypto/subtle"

	"golang.org/x/crypto/scrypt"
)

const (
	saltSize          = 16
	scryptCost        = 1 << 14
	scryptBlockSize   = 8
	scryptParallelism = 1
	digestSize        = 64
)

type Scrypt struct{}

func (Scrypt) Hash(password string) ([]byte, error) {
	salt := make([]byte, saltSize)
	rand.Read(salt)
	digest, err := scrypt.Key([]byte(password), salt, scryptCost, scryptBlockSize, scryptParallelism, digestSize)
	return append(salt, digest...), err
}

func (Scrypt) Matches(hash []byte, password string) bool {
	if len(hash) != saltSize+digestSize {
		return false
	}
	digest, err := scrypt.Key([]byte(password), hash[:saltSize], scryptCost, scryptBlockSize, scryptParallelism, digestSize)
	return err == nil && subtle.ConstantTimeCompare(digest, hash[saltSize:]) == 1
}
