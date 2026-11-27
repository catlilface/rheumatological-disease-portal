package idempotency

import "crypto/sha256"

type Fingerprint [sha256.Size]byte

func FingerprintRequest(method, escapedPath string, body []byte) Fingerprint {
	return sha256.Sum256([]byte(method + ":" + escapedPath + ":" + string(body)))
}
