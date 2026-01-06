package validation

import (
	"regexp"
	"strings"
	"unicode"
)

// PasswordOptions configures password validation requirements.
type PasswordOptions struct {
	MinLength        int
	MaxLength        int
	RequireUppercase bool
	RequireLowercase bool
	RequireDigit     bool
	RequireSpecial   bool
	SpecialChars     string
	DisallowSpaces   bool
}

// DefaultPasswordOptions returns default password options.
func DefaultPasswordOptions() PasswordOptions {
	return PasswordOptions{
		MinLength:        8,
		MaxLength:        128,
		RequireUppercase: true,
		RequireLowercase: true,
		RequireDigit:     true,
		RequireSpecial:   true,
		SpecialChars:     "!@#$%^&*()_+-=[]{}|;:,.<>?~`",
		DisallowSpaces:   true,
	}
}

// WeakPasswordOptions returns weak password requirements.
func WeakPasswordOptions() PasswordOptions {
	return PasswordOptions{
		MinLength:        6,
		MaxLength:        128,
		RequireUppercase: false,
		RequireLowercase: false,
		RequireDigit:     false,
		RequireSpecial:   false,
		SpecialChars:     "!@#$%^&*()_+-=[]{}|;:,.<>?~`",
		DisallowSpaces:   true,
	}
}

// ModeratePasswordOptions returns moderate password requirements.
func ModeratePasswordOptions() PasswordOptions {
	return PasswordOptions{
		MinLength:        8,
		MaxLength:        128,
		RequireUppercase: true,
		RequireLowercase: true,
		RequireDigit:     true,
		RequireSpecial:   false,
		SpecialChars:     "!@#$%^&*()_+-=[]{}|;:,.<>?~`",
		DisallowSpaces:   true,
	}
}

// StrongPasswordOptions returns strong password requirements.
func StrongPasswordOptions() PasswordOptions {
	return PasswordOptions{
		MinLength:        12,
		MaxLength:        128,
		RequireUppercase: true,
		RequireLowercase: true,
		RequireDigit:     true,
		RequireSpecial:   true,
		SpecialChars:     "!@#$%^&*()_+-=[]{}|;:,.<>?~`",
		DisallowSpaces:   true,
	}
}

// EnterprisePasswordOptions returns enterprise password requirements.
func EnterprisePasswordOptions() PasswordOptions {
	return PasswordOptions{
		MinLength:        16,
		MaxLength:        256,
		RequireUppercase: true,
		RequireLowercase: true,
		RequireDigit:     true,
		RequireSpecial:   true,
		SpecialChars:     "!@#$%^&*()_+-=[]{}|;:,.<>?~`",
		DisallowSpaces:   true,
	}
}

// StrongPassword validates password strength based on configurable requirements.
func StrongPassword(opts ...func(*passwordOpts)) Validator {
	o := &passwordOpts{
		options: DefaultPasswordOptions(),
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			var errors []string
			po := o.options

			// Length checks
			if len(s) < po.MinLength {
				errors = append(errors, "password must be at least "+itoa(po.MinLength)+" characters")
			}

			if len(s) > po.MaxLength {
				errors = append(errors, "password must be at most "+itoa(po.MaxLength)+" characters")
			}

			// Space check
			if po.DisallowSpaces && strings.Contains(s, " ") {
				errors = append(errors, "password cannot contain spaces")
			}

			// Character type checks
			if po.RequireUppercase && !hasUppercase(s) {
				errors = append(errors, "password must contain at least one uppercase letter")
			}

			if po.RequireLowercase && !hasLowercase(s) {
				errors = append(errors, "password must contain at least one lowercase letter")
			}

			if po.RequireDigit && !hasDigit(s) {
				errors = append(errors, "password must contain at least one digit")
			}

			if po.RequireSpecial && !hasSpecial(s, po.SpecialChars) {
				errors = append(errors, "password must contain at least one special character")
			}

			if len(errors) > 0 {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failure(strings.Join(errors, "; "))
			}

			return Success(s)
		},
	}
}

type passwordOpts struct {
	options      PasswordOptions
	errorMessage string
}

// WithPasswordOptions sets custom password options.
func WithPasswordOptions(opts PasswordOptions) func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options = opts
	}
}

// WithMinPasswordLength sets minimum password length.
func WithMinPasswordLength(min int) func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.MinLength = min
	}
}

// WithMaxPasswordLength sets maximum password length.
func WithMaxPasswordLength(max int) func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.MaxLength = max
	}
}

// WithPasswordError sets a custom error message.
func WithPasswordError(msg string) func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.errorMessage = msg
	}
}

// WithoutUppercase removes uppercase requirement.
func WithoutUppercase() func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.RequireUppercase = false
	}
}

// WithoutLowercase removes lowercase requirement.
func WithoutLowercase() func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.RequireLowercase = false
	}
}

// WithoutDigit removes digit requirement.
func WithoutDigit() func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.RequireDigit = false
	}
}

// WithoutSpecial removes special character requirement.
func WithoutSpecial() func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.RequireSpecial = false
	}
}

// AllowSpaces allows spaces in passwords.
func AllowSpaces() func(*passwordOpts) {
	return func(o *passwordOpts) {
		o.options.DisallowSpaces = false
	}
}

// Helper functions

func hasUppercase(s string) bool {
	for _, r := range s {
		if unicode.IsUpper(r) {
			return true
		}
	}
	return false
}

func hasLowercase(s string) bool {
	for _, r := range s {
		if unicode.IsLower(r) {
			return true
		}
	}
	return false
}

func hasDigit(s string) bool {
	for _, r := range s {
		if unicode.IsDigit(r) {
			return true
		}
	}
	return false
}

func hasSpecial(s, specialChars string) bool {
	specialSet := make(map[rune]struct{}, len(specialChars))
	for _, r := range specialChars {
		specialSet[r] = struct{}{}
	}

	for _, r := range s {
		if _, ok := specialSet[r]; ok {
			return true
		}
	}
	return false
}

// itoa is a simple int to string conversion
func itoa(i int) string {
	if i == 0 {
		return "0"
	}

	var negative bool
	if i < 0 {
		negative = true
		i = -i
	}

	var digits []byte
	for i > 0 {
		digits = append([]byte{byte('0' + i%10)}, digits...)
		i /= 10
	}

	if negative {
		return "-" + string(digits)
	}
	return string(digits)
}

// PasswordStrengthScore calculates a password strength score (0-100).
func PasswordStrengthScore(password string, specialChars string) int {
	if specialChars == "" {
		specialChars = "!@#$%^&*()_+-=[]{}|;:,.<>?~`"
	}

	score := 0

	// Length contribution (up to 30 points)
	lengthScore := len(password) * 2
	if lengthScore > 30 {
		lengthScore = 30
	}
	score += lengthScore

	// Character variety (up to 40 points)
	variety := 0
	if hasLowercase(password) {
		variety++
	}
	if hasUppercase(password) {
		variety++
	}
	if hasDigit(password) {
		variety++
	}
	if hasSpecial(password, specialChars) {
		variety++
	}
	score += variety * 10

	// Unique character ratio (up to 20 points)
	if len(password) > 0 {
		unique := make(map[rune]struct{})
		for _, r := range password {
			unique[r] = struct{}{}
		}
		uniqueRatio := float64(len(unique)) / float64(len(password))
		score += int(uniqueRatio * 20)
	}

	// No common patterns bonus (up to 10 points)
	commonPatterns := []*regexp.Regexp{
		regexp.MustCompile(`^123`),
		regexp.MustCompile(`(?i)abc`),
		regexp.MustCompile(`(?i)qwerty`),
		regexp.MustCompile(`(?i)password`),
		regexp.MustCompile(`(.)\1{2,}`), // Repeated characters
	}

	hasCommon := false
	for _, pattern := range commonPatterns {
		if pattern.MatchString(password) {
			hasCommon = true
			break
		}
	}
	if !hasCommon {
		score += 10
	}

	if score > 100 {
		score = 100
	}

	return score
}
