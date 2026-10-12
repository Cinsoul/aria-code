package training

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
)

type jsonPair struct {
	key   string
	value any
}
type jsonObject []jsonPair

func readValue(d *json.Decoder, depth int) (any, error) {
	if depth > 256 {
		return nil, errors.New("JSON nesting exceeds 256 levels")
	}
	token, err := d.Token()
	if err != nil {
		return nil, err
	}
	if delimiter, ok := token.(json.Delim); ok {
		switch delimiter {
		case '{':
			out := jsonObject{}
			for d.More() {
				key, err := d.Token()
				if err != nil {
					return nil, err
				}
				value, err := readValue(d, depth+1)
				if err != nil {
					return nil, err
				}
				out = append(out, jsonPair{key.(string), value})
			}
			_, err := d.Token()
			return out, err
		case '[':
			out := []any{}
			for d.More() {
				value, err := readValue(d, depth+1)
				if err != nil {
					return nil, err
				}
				out = append(out, value)
			}
			_, err := d.Token()
			return out, err
		}
		return nil, errors.New("invalid JSON delimiter")
	}
	return token, nil
}
func quote(text string, ascii bool) string {
	var out strings.Builder
	out.WriteByte('"')
	for _, r := range text {
		switch r {
		case '"':
			out.WriteString(`\"`)
		case '\\':
			out.WriteString(`\\`)
		case '\b':
			out.WriteString(`\b`)
		case '\f':
			out.WriteString(`\f`)
		case '\n':
			out.WriteString(`\n`)
		case '\r':
			out.WriteString(`\r`)
		case '\t':
			out.WriteString(`\t`)
		default:
			if r < 32 || (ascii && r >= 127) {
				if r <= 0xffff {
					out.WriteString(`\u` + hex4(uint16(r)))
				} else {
					a, b := utf16.EncodeRune(r)
					out.WriteString(`\u` + hex4(uint16(a)) + `\u` + hex4(uint16(b)))
				}
			} else {
				out.WriteRune(r)
			}
		}
	}
	out.WriteByte('"')
	return out.String()
}
func hex4(value uint16) string {
	digits := strconv.FormatUint(uint64(value), 16)
	return strings.Repeat("0", 4-len(digits)) + digits
}
func pythonNumber(value json.Number) (string, error) {
	s := value.String()
	if !strings.ContainsAny(s, ".eE") {
		return s, nil
	}
	n, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return "", err
	}
	exponential := strconv.FormatFloat(n, 'e', -1, 64)
	_, suffix, _ := strings.Cut(exponential, "e")
	exponent, err := strconv.Atoi(suffix)
	if err != nil {
		return "", err
	}
	if exponent < -4 || exponent >= 16 {
		return exponential, nil
	}
	text := strconv.FormatFloat(n, 'f', -1, 64)
	if !strings.Contains(text, ".") {
		text += ".0"
	}
	return text, nil
}
func encodeValue(b *strings.Builder, value any, sorted, ascii bool) error {
	switch value := value.(type) {
	case jsonObject:
		pairs := append(jsonObject{}, value...)
		if sorted {
			sort.SliceStable(pairs, func(i, j int) bool { return pairs[i].key < pairs[j].key })
		}
		b.WriteByte('{')
		for i, pair := range pairs {
			if i > 0 {
				b.WriteString(", ")
			}
			b.WriteString(quote(pair.key, ascii))
			b.WriteString(": ")
			if err := encodeValue(b, pair.value, sorted, ascii); err != nil {
				return err
			}
		}
		b.WriteByte('}')
	case []any:
		b.WriteByte('[')
		for i, item := range value {
			if i > 0 {
				b.WriteString(", ")
			}
			if err := encodeValue(b, item, sorted, ascii); err != nil {
				return err
			}
		}
		b.WriteByte(']')
	case string:
		b.WriteString(quote(value, ascii))
	case json.Number:
		text, err := pythonNumber(value)
		if err != nil {
			return err
		}
		b.WriteString(text)
	case bool:
		if value {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case nil:
		b.WriteString("null")
	default:
		return errors.New("invalid JSON scalar")
	}
	return nil
}
func pythonJSON(raw []byte, sorted, ascii bool) (string, error) {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	value, err := readValue(d, 0)
	if err != nil {
		return "", err
	}
	if _, err := d.Token(); err != io.EOF {
		return "", errors.New("unexpected trailing JSON value")
	}
	var b strings.Builder
	if err := encodeValue(&b, value, sorted, ascii); err != nil {
		return "", err
	}
	return b.String(), nil
}
