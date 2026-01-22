package validation

import (
	"net"
	"net/url"
	"regexp"
	"strings"
)

// Email validates that a string is a valid email address.
func Email(opts ...func(*emailOpts)) Validator {
	o := &emailOpts{
		normalize:    true,
		errorMessage: "invalid email address",
	}
	for _, opt := range opts {
		opt(o)
	}

	// RFC 5322 compliant email regex (simplified but robust)
	emailRegex := regexp.MustCompile(
		`^[a-zA-Z0-9.!#$%&'*+/=?^_` + "`" + `{|}~-]+` +
			`@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?` +
			`(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$`,
	)

	return &StringValidator{
		validate: func(s string) ValidationResult {
			email := strings.TrimSpace(s)
			if email == "" {
				return Failure(o.errorMessage)
			}

			// Check length constraints
			if len(email) > 254 {
				return Failure(o.errorMessage)
			}

			// Check local part length
			atIdx := strings.Index(email, "@")
			if atIdx == -1 || atIdx > 64 {
				return Failure(o.errorMessage)
			}

			if !emailRegex.MatchString(email) {
				return Failure(o.errorMessage)
			}

			if o.normalize {
				email = strings.ToLower(email)
			}

			return Success(email)
		},
	}
}

type emailOpts struct {
	normalize    bool
	errorMessage string
}

// WithoutNormalize disables email normalization (lowercase).
func WithoutNormalize() func(*emailOpts) {
	return func(o *emailOpts) {
		o.normalize = false
	}
}

// WithEmailError sets a custom error message for Email.
func WithEmailError(msg string) func(*emailOpts) {
	return func(o *emailOpts) {
		o.errorMessage = msg
	}
}

// URL validates that a string is a valid URL.
func URL(opts ...func(*urlOpts)) Validator {
	o := &urlOpts{
		requireTLD:     true,
		allowedSchemes: map[string]struct{}{"http": {}, "https": {}},
		errorMessage:   "invalid URL",
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			urlStr := strings.TrimSpace(s)
			if urlStr == "" {
				return Failure(o.errorMessage)
			}

			parsed, err := url.Parse(urlStr)
			if err != nil {
				return Failure(o.errorMessage)
			}

			// Check scheme
			if parsed.Scheme == "" {
				return Failure(o.errorMessage)
			}

			if _, ok := o.allowedSchemes[strings.ToLower(parsed.Scheme)]; !ok {
				schemes := make([]string, 0, len(o.allowedSchemes))
				for s := range o.allowedSchemes {
					schemes = append(schemes, s)
				}
				return Failuref("URL scheme must be one of: %s", strings.Join(schemes, ", "))
			}

			// Check netloc (hostname)
			if parsed.Host == "" {
				return Failure(o.errorMessage)
			}

			// Check for TLD if required
			if o.requireTLD {
				hostname := parsed.Hostname()
				if !strings.Contains(hostname, ".") && strings.ToLower(hostname) != "localhost" {
					return Failure(o.errorMessage)
				}
			}

			return Success(urlStr)
		},
	}
}

type urlOpts struct {
	requireTLD     bool
	allowedSchemes map[string]struct{}
	errorMessage   string
}

// WithoutTLD allows URLs without a top-level domain.
func WithoutTLD() func(*urlOpts) {
	return func(o *urlOpts) {
		o.requireTLD = false
	}
}

// WithSchemes sets allowed URL schemes.
func WithSchemes(schemes ...string) func(*urlOpts) {
	return func(o *urlOpts) {
		o.allowedSchemes = make(map[string]struct{}, len(schemes))
		for _, s := range schemes {
			o.allowedSchemes[strings.ToLower(s)] = struct{}{}
		}
	}
}

// WithURLError sets a custom error message for URL.
func WithURLError(msg string) func(*urlOpts) {
	return func(o *urlOpts) {
		o.errorMessage = msg
	}
}

// IPAddress validates that a string is a valid IP address.
func IPAddress(opts ...func(*ipOpts)) Validator {
	o := &ipOpts{
		version: 0, // 0 = any, 4 = IPv4, 6 = IPv6
	}
	for _, opt := range opts {
		opt(o)
	}

	return &StringValidator{
		validate: func(s string) ValidationResult {
			ipStr := strings.TrimSpace(s)
			if ipStr == "" {
				return Failure(o.getErrorMessage())
			}

			ip := net.ParseIP(ipStr)
			if ip == nil {
				return Failure(o.getErrorMessage())
			}

			// Check version if specified
			isIPv4 := ip.To4() != nil
			if o.version == 4 && !isIPv4 {
				return Failure("value must be a valid IPv4 address")
			}
			if o.version == 6 && isIPv4 {
				return Failure("value must be a valid IPv6 address")
			}

			return Success(ipStr)
		},
	}
}

type ipOpts struct {
	version      int // 0 = any, 4 = IPv4, 6 = IPv6
	errorMessage string
}

func (o *ipOpts) getErrorMessage() string {
	if o.errorMessage != "" {
		return o.errorMessage
	}
	switch o.version {
	case 4:
		return "value must be a valid IPv4 address"
	case 6:
		return "value must be a valid IPv6 address"
	default:
		return "value must be a valid IP address"
	}
}

// IPv4Only restricts IPAddress to IPv4 only.
func IPv4Only() func(*ipOpts) {
	return func(o *ipOpts) {
		o.version = 4
	}
}

// IPv6Only restricts IPAddress to IPv6 only.
func IPv6Only() func(*ipOpts) {
	return func(o *ipOpts) {
		o.version = 6
	}
}

// WithIPError sets a custom error message for IPAddress.
func WithIPError(msg string) func(*ipOpts) {
	return func(o *ipOpts) {
		o.errorMessage = msg
	}
}

// Hostname validates that a string is a valid hostname.
func Hostname(opts ...func(*hostnameOpts)) Validator {
	o := &hostnameOpts{
		allowIP:      false,
		requireTLD:   false,
		errorMessage: "invalid hostname",
	}
	for _, opt := range opts {
		opt(o)
	}

	// RFC 1123 hostname pattern
	hostnameRegex := regexp.MustCompile(
		`^(?i)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?` +
			`(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$`,
	)

	return &StringValidator{
		validate: func(s string) ValidationResult {
			hostname := strings.TrimSpace(strings.ToLower(s))
			if hostname == "" {
				return Failure(o.errorMessage)
			}

			// Check total length
			if len(hostname) > 253 {
				return Failure(o.errorMessage)
			}

			// Check if it's an IP address
			if o.allowIP {
				if ip := net.ParseIP(hostname); ip != nil {
					return Success(hostname)
				}
			}

			// Validate hostname format
			if !hostnameRegex.MatchString(hostname) {
				return Failure(o.errorMessage)
			}

			// Check TLD requirement
			if o.requireTLD && !strings.Contains(hostname, ".") {
				return Failure("hostname must have a top-level domain")
			}

			return Success(hostname)
		},
	}
}

type hostnameOpts struct {
	allowIP      bool
	requireTLD   bool
	errorMessage string
}

// AllowIP allows IP addresses as hostnames.
func AllowIP() func(*hostnameOpts) {
	return func(o *hostnameOpts) {
		o.allowIP = true
	}
}

// RequireTLD requires hostnames to have a TLD.
func RequireTLD() func(*hostnameOpts) {
	return func(o *hostnameOpts) {
		o.requireTLD = true
	}
}

// WithHostnameError sets a custom error message for Hostname.
func WithHostnameError(msg string) func(*hostnameOpts) {
	return func(o *hostnameOpts) {
		o.errorMessage = msg
	}
}
