package validation

import (
	"regexp"
	"strings"
	"unicode"
)

// StringValidator is a validator specifically for string values.
type StringValidator struct {
	validate func(string) ValidationResult
}

// Validate implements the Validator interface.
func (v *StringValidator) Validate(value any) ValidationResult {
	s, ok := value.(string)
	if !ok {
		return Failure("value must be a string")
	}
	return v.validate(s)
}

// NotEmpty validates that a string is not empty or whitespace-only.
// The returned value is trimmed.
func NotEmpty(opts ...func(*notEmptyOpts)) Validator {
	o := &notEmptyOpts{
		errorMessage: "value cannot be empty",
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			trimmed := strings.TrimSpace(s)
			if trimmed == "" {
				return Failure(o.errorMessage)
			}
			return Success(trimmed)
		},
	}
}

type notEmptyOpts struct {
	errorMessage string
}

// WithNotEmptyError sets a custom error message for NotEmpty.
func WithNotEmptyError(msg string) func(*notEmptyOpts) {
	return func(o *notEmptyOpts) {
		o.errorMessage = msg
	}
}

// Length validates that a string length is within a range.
func Length(minLen, maxLen int, opts ...func(*lengthOpts)) Validator {
	o := &lengthOpts{}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			l := len(s)
			if l < minLen {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failuref("value must be at least %d characters", minLen)
			}
			if maxLen > 0 && l > maxLen {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failuref("value must be at most %d characters", maxLen)
			}
			return Success(s)
		},
	}
}

type lengthOpts struct {
	errorMessage string
}

// WithLengthError sets a custom error message for Length.
func WithLengthError(msg string) func(*lengthOpts) {
	return func(o *lengthOpts) {
		o.errorMessage = msg
	}
}

// MinLength validates minimum string length.
func MinLength(min int, opts ...func(*lengthOpts)) Validator {
	return Length(min, 0, opts...)
}

// MaxLength validates maximum string length.
func MaxLength(max int, opts ...func(*lengthOpts)) Validator {
	return Length(0, max, opts...)
}

// Match validates that a string matches a regex pattern.
func Match(pattern string, opts ...func(*matchOpts)) Validator {
	o := &matchOpts{
		errorMessage: "value does not match required pattern",
	}
	for _, opt := range opts {
		opt(o)
	}

	re := regexp.MustCompile(pattern)

	return &StringValidator{
		validate: func(s string) ValidationResult {
			if !re.MatchString(s) {
				return Failure(o.errorMessage)
			}
			return Success(s)
		},
	}
}

type matchOpts struct {
	errorMessage string
}

// WithMatchError sets a custom error message for Match.
func WithMatchError(msg string) func(*matchOpts) {
	return func(o *matchOpts) {
		o.errorMessage = msg
	}
}

// Alphanumeric validates that a string contains only alphanumeric characters.
func Alphanumeric(opts ...func(*alphanumericOpts)) Validator {
	o := &alphanumericOpts{
		allowUnderscore: false,
		allowDash:       false,
		errorMessage:    "value must contain only alphanumeric characters",
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			if s == "" {
				return Failure("value cannot be empty")
			}

			for _, r := range s {
				if unicode.IsLetter(r) || unicode.IsDigit(r) {
					continue
				}
				if o.allowUnderscore && r == '_' {
					continue
				}
				if o.allowDash && r == '-' {
					continue
				}
				return Failure(o.errorMessage)
			}
			return Success(s)
		},
	}
}

type alphanumericOpts struct {
	allowUnderscore bool
	allowDash       bool
	errorMessage    string
}

// WithUnderscore allows underscores in Alphanumeric.
func WithUnderscore() func(*alphanumericOpts) {
	return func(o *alphanumericOpts) {
		o.allowUnderscore = true
	}
}

// WithDash allows dashes in Alphanumeric.
func WithDash() func(*alphanumericOpts) {
	return func(o *alphanumericOpts) {
		o.allowDash = true
	}
}

// WithAlphanumericError sets a custom error message for Alphanumeric.
func WithAlphanumericError(msg string) func(*alphanumericOpts) {
	return func(o *alphanumericOpts) {
		o.errorMessage = msg
	}
}

// Slug validates that a string is a valid URL slug.
// A valid slug contains only lowercase letters, numbers, and hyphens,
// starts and ends with alphanumeric, and has no consecutive hyphens.
func Slug(opts ...func(*slugOpts)) Validator {
	o := &slugOpts{
		errorMessage: "value must be a valid URL slug",
	}
	for _, opt := range opts {
		opt(o)
	}

	slugRegex := regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)

	return &StringValidator{
		validate: func(s string) ValidationResult {
			if s == "" {
				return Failure("value cannot be empty")
			}
			if !slugRegex.MatchString(s) {
				return Failure(o.errorMessage)
			}
			return Success(s)
		},
	}
}

type slugOpts struct {
	errorMessage string
}

// WithSlugError sets a custom error message for Slug.
func WithSlugError(msg string) func(*slugOpts) {
	return func(o *slugOpts) {
		o.errorMessage = msg
	}
}

// In validates that a value is in an allowed set.
func In(options []string, opts ...func(*inOpts)) Validator {
	o := &inOpts{
		caseSensitive: true,
	}
	for _, opt := range opts {
		opt(o)
	}

	// Build set for fast lookup
	optionSet := make(map[string]struct{}, len(options))
	for _, opt := range options {
		key := opt
		if !o.caseSensitive {
			key = strings.ToLower(opt)
		}
		optionSet[key] = struct{}{}
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			checkValue := s
			if !o.caseSensitive {
				checkValue = strings.ToLower(s)
			}

			if _, ok := optionSet[checkValue]; !ok {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failuref("value must be one of: %s", strings.Join(options, ", "))
			}
			return Success(s)
		},
	}
}

type inOpts struct {
	caseSensitive bool
	errorMessage  string
}

// CaseInsensitive makes In comparison case-insensitive.
func CaseInsensitive() func(*inOpts) {
	return func(o *inOpts) {
		o.caseSensitive = false
	}
}

// WithInError sets a custom error message for In.
func WithInError(msg string) func(*inOpts) {
	return func(o *inOpts) {
		o.errorMessage = msg
	}
}

// Trimmed validates and trims whitespace from a string.
func Trimmed(opts ...func(*trimmedOpts)) Validator {
	o := &trimmedOpts{
		allowEmpty: false,
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			trimmed := strings.TrimSpace(s)
			if !o.allowEmpty && trimmed == "" {
				return Failure("value cannot be empty")
			}
			return Success(trimmed)
		},
	}
}

type trimmedOpts struct {
	allowEmpty bool
}

// AllowEmpty allows empty strings in Trimmed.
func AllowEmpty() func(*trimmedOpts) {
	return func(o *trimmedOpts) {
		o.allowEmpty = true
	}
}
