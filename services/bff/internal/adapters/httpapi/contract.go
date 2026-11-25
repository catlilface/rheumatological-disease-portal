package httpapi

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"strings"

	js "github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

// Bind by operationId so a missing handler or request schema fails startup, not a browser workflow.
type endpoint struct {
	pattern string
	body    *js.Schema
	params  []parameter
}
type parameter struct {
	Ref      string `yaml:"$ref"`
	In, Name string
	Required bool
	Schema   map[string]any
	checked  *js.Schema
	scalar   string
}
type operation struct {
	ID         string `yaml:"operationId"`
	Parameters []parameter
	Body       struct {
		Content map[string]struct {
			Schema struct {
				Ref string `yaml:"$ref"`
			}
		}
	} `yaml:"requestBody"`
}
type contract map[string]endpoint

const (
	apiBase    = "/api/v1"
	schemaBase = "https://contract.invalid/"
)

func loadContract(files fs.FS) (contract, error) {
	var spec struct {
		Paths      map[string]map[string]yaml.Node
		Components struct{ Parameters map[string]parameter }
	}
	read := func(path string, v any) error {
		data, err := fs.ReadFile(files, path)
		if err != nil {
			return err
		}
		return yaml.Unmarshal(data, v)
	}
	if err := read("bff-v1.openapi.yaml", &spec); err != nil {
		return nil, err
	}
	var schemas map[string]any
	if err := read("schemas.yaml", &schemas); err != nil {
		return nil, err
	}
	compiler := js.NewCompiler()
	compiler.AssertFormat()
	add := func(url string, x any) error {
		b, err := json.Marshal(x)
		if err != nil {
			return err
		}
		doc, err := js.UnmarshalJSON(bytes.NewReader(b))
		if err != nil {
			return err
		}
		return compiler.AddResource(schemaBase+url, doc)
	}
	if err := add("schemas.yaml", schemas); err != nil {
		return nil, err
	}
	out := contract{}
	for path, methods := range spec.Paths {
		var shared []parameter
		if n, ok := methods["parameters"]; ok {
			if err := n.Decode(&shared); err != nil {
				return nil, err
			}
		}
		for method, node := range methods {
			if method == "parameters" {
				continue
			}
			var op operation
			if err := node.Decode(&op); err != nil {
				return nil, err
			}
			e := endpoint{pattern: strings.ToUpper(method) + " " + apiBase + path}
			if body, ok := op.Body.Content["application/json"]; ok {
				var err error
				e.body, err = compiler.Compile(schemaBase + body.Schema.Ref)
				if err != nil {
					return nil, err
				}
			}
			for i, p := range append(append([]parameter{}, shared...), op.Parameters...) {
				if p.Ref != "" {
					var ok bool
					p, ok = spec.Components.Parameters[strings.TrimPrefix(p.Ref, "#/components/parameters/")]
					if !ok {
						return nil, fmt.Errorf("unknown parameter in %s", op.ID)
					}
				}
				url := fmt.Sprintf("%s-%d.json", op.ID, i)
				if err := add(url, p.Schema); err != nil {
					return nil, err
				}
				var err error
				p.checked, err = compiler.Compile(schemaBase + url)
				if err != nil {
					return nil, err
				}
				p.scalar, _ = p.Schema["type"].(string)
				switch p.Schema["$ref"] {
				case "schemas.yaml#/$defs/Version":
					p.scalar = "integer"
				case "schemas.yaml#/$defs/Id":
					p.scalar = "uuid"
				}
				if p.Schema["format"] == "uuid" {
					p.scalar = "uuid"
				}
				e.params = append(e.params, p)
			}
			if _, ok := out[op.ID]; ok || op.ID == "" {
				return nil, fmt.Errorf("invalid operation ID %q", op.ID)
			}
			out[op.ID] = e
		}
	}
	return out, nil
}
