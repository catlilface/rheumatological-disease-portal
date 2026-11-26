package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

type CORS struct {
	Origins     []string `json:"allow_origins"`
	Methods     []string `json:"allow_methods"`
	Headers     []string `json:"allow_headers"`
	Credentials bool     `json:"allow_credentials"`
	Expose      []string `json:"expose_headers"`
	MaxAge      int      `json:"max_age"`
}
type Settings struct {
	Name, ModeratorPassword string
	Debug                   bool
	Hosts                   []string
	CORS                    CORS
}

func Root() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for dir := cwd; ; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, "contracts/http/bff-v1.openapi.yaml")); err == nil {
			return dir, nil
		}
		if dir == filepath.Dir(dir) {
			return "", errors.New("contracts/http not found; start from the repository or image working directory")
		}
	}
}
func Load(root string) (Settings, error) {
	s := Settings{Name: "Rheumatological Disease Portal", Hosts: []string{"localhost", "127.0.0.1", "bff", "server"}, CORS: CORS{Methods: []string{"GET"}, MaxAge: 600}}
	file, err := godotenv.Read(filepath.Join(root, ".env"))
	if err != nil && !os.IsNotExist(err) {
		return s, errors.New("invalid .env")
	}
	for _, source := range []map[string]string{file, environment()} {
		for _, k := range []string{"APP_NAME", "MOCK_MODERATOR_PASSWORD", "DEBUG", "ALLOWED_HOSTS", "CORS", "CORS__ALLOW_ORIGINS", "CORS__ALLOW_METHODS", "CORS__ALLOW_HEADERS", "CORS__ALLOW_CREDENTIALS", "CORS__EXPOSE_HEADERS", "CORS__MAX_AGE"} {
			v, ok := source[k]
			if !ok {
				continue
			}
			var err error
			switch k {
			case "APP_NAME":
				s.Name = v
			case "MOCK_MODERATOR_PASSWORD":
				s.ModeratorPassword = v
			case "DEBUG":
				s.Debug, err = strconv.ParseBool(v)
			case "CORS__ALLOW_CREDENTIALS":
				s.CORS.Credentials, err = strconv.ParseBool(v)
			case "CORS__MAX_AGE":
				s.CORS.MaxAge, err = strconv.Atoi(v)
			default:
				var dst any
				switch k {
				case "ALLOWED_HOSTS":
					dst = &s.Hosts
				case "CORS":
					dst = &s.CORS
				case "CORS__ALLOW_ORIGINS":
					dst = &s.CORS.Origins
				case "CORS__ALLOW_METHODS":
					dst = &s.CORS.Methods
				case "CORS__ALLOW_HEADERS":
					dst = &s.CORS.Headers
				case "CORS__EXPOSE_HEADERS":
					dst = &s.CORS.Expose
				}
				err = json.Unmarshal([]byte(v), dst)
			}
			if err != nil {
				return s, fmt.Errorf("invalid %s", k)
			}
		}
	}
	if len(s.Hosts) == 0 || s.CORS.MaxAge < 0 {
		return s, errors.New("invalid host list or CORS max age")
	}
	if s.CORS.Credentials && (slices.Contains(s.CORS.Origins, "*") || slices.Contains(s.CORS.Methods, "*") || slices.Contains(s.CORS.Headers, "*")) {
		return s, errors.New("credentialed CORS forbids wildcards")
	}
	return s, nil
}
func environment() map[string]string {
	m := map[string]string{}
	for _, item := range os.Environ() {
		k, v, _ := strings.Cut(item, "=")
		m[k] = v
	}
	return m
}
