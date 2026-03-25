package identity

import (
	"context"
	"io"
	"testing"

	log "github.com/sirupsen/logrus"
)

// ---------------------------------------------------------------------------
// Test logger helper
// ---------------------------------------------------------------------------

// newTestLogger returns a logrus.Logger that discards all output.
func newTestLogger() *log.Logger {
	l := log.New()
	l.SetOutput(io.Discard)
	return l
}

// ---------------------------------------------------------------------------
// ParseSPIFFEID
// ---------------------------------------------------------------------------

func TestParseSPIFFEID_Valid(t *testing.T) {
	td, cluster, ns, svc, err := ParseSPIFFEID("spiffe://acme.tobogganing.io/aws-east/backend/api-server")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if td != "acme.tobogganing.io" {
		t.Errorf("trust domain = %q, want %q", td, "acme.tobogganing.io")
	}
	if cluster != "aws-east" {
		t.Errorf("cluster = %q, want %q", cluster, "aws-east")
	}
	if ns != "backend" {
		t.Errorf("namespace = %q, want %q", ns, "backend")
	}
	if svc != "api-server" {
		t.Errorf("service = %q, want %q", svc, "api-server")
	}
}

func TestParseSPIFFEID_SimpleLabels(t *testing.T) {
	td, cluster, ns, svc, err := ParseSPIFFEID("spiffe://corp.tobogganing.io/c1/ns/gateway")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if td != "corp.tobogganing.io" {
		t.Errorf("trust domain = %q", td)
	}
	if cluster != "c1" {
		t.Errorf("cluster = %q", cluster)
	}
	if ns != "ns" {
		t.Errorf("namespace = %q", ns)
	}
	if svc != "gateway" {
		t.Errorf("service = %q", svc)
	}
}

func TestParseSPIFFEID_InvalidScheme(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("https://acme.tobogganing.io/c/n/s")
	if err == nil {
		t.Error("expected error for non-spiffe scheme")
	}
}

func TestParseSPIFFEID_HTTPScheme(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("http://acme.tobogganing.io/c/n/s")
	if err == nil {
		t.Error("expected error for http scheme")
	}
}

func TestParseSPIFFEID_TooFewSegments(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io/only-one")
	if err == nil {
		t.Error("expected error for too few path segments")
	}
}

func TestParseSPIFFEID_TwoSegments(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io/cluster/namespace")
	if err == nil {
		t.Error("expected error for two path segments (need three)")
	}
}

func TestParseSPIFFEID_NoPath(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io")
	if err == nil {
		t.Error("expected error for no path segments")
	}
}

func TestParseSPIFFEID_EmptySegment_Cluster(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io//ns/s")
	if err == nil {
		t.Error("expected error for empty cluster segment")
	}
}

func TestParseSPIFFEID_EmptySegment_Namespace(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io/c//s")
	if err == nil {
		t.Error("expected error for empty namespace segment")
	}
}

func TestParseSPIFFEID_EmptySegment_Service(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("spiffe://acme.tobogganing.io/c/ns/")
	if err == nil {
		t.Error("expected error for empty service segment")
	}
}

func TestParseSPIFFEID_EmptyString(t *testing.T) {
	_, _, _, _, err := ParseSPIFFEID("")
	if err == nil {
		t.Error("expected error for empty SPIFFE ID")
	}
}

func TestParseSPIFFEID_EmptyTrustDomain(t *testing.T) {
	// spiffe:/// with no host produces empty trust domain
	_, _, _, _, err := ParseSPIFFEID("spiffe:///c/ns/svc")
	if err == nil {
		t.Error("expected error for empty trust domain")
	}
}

func TestParseSPIFFEID_HyphensAndDots(t *testing.T) {
	td, cluster, ns, svc, err := ParseSPIFFEID(
		"spiffe://my-org.tobogganing.io/eks-us-east-1/prod-namespace/auth-service",
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if td != "my-org.tobogganing.io" {
		t.Errorf("trust domain = %q", td)
	}
	if cluster != "eks-us-east-1" {
		t.Errorf("cluster = %q", cluster)
	}
	if ns != "prod-namespace" {
		t.Errorf("namespace = %q", ns)
	}
	if svc != "auth-service" {
		t.Errorf("service = %q", svc)
	}
}

// ---------------------------------------------------------------------------
// NewValidator — construction and priority ordering
// ---------------------------------------------------------------------------

func TestNewValidator_DisabledProvidersSkipped(t *testing.T) {
	l := newTestLogger()
	configs := []ProviderConfig{
		{Type: ProviderK8sSA, Priority: 0, Issuer: "https://k8s.example.com", Enabled: false},
	}
	v := NewValidator(configs, l)
	if len(v.providers) != 0 {
		t.Errorf("expected 0 providers when all disabled, got %d", len(v.providers))
	}
}

func TestNewValidator_SPIFFENotInTokenProviders(t *testing.T) {
	l := newTestLogger()
	configs := []ProviderConfig{
		{Type: ProviderSPIFFE, Priority: 0, Enabled: true},
	}
	v := NewValidator(configs, l)
	// SPIFFE is registered in v.spiffe, NOT in v.providers (token-based).
	if len(v.providers) != 0 {
		t.Errorf("expected 0 token providers for SPIFFE-only config, got %d", len(v.providers))
	}
	if v.spiffe == nil {
		t.Error("expected v.spiffe to be non-nil")
	}
}

func TestNewValidator_SPIFFEVerifierIsSet(t *testing.T) {
	l := newTestLogger()
	configs := []ProviderConfig{
		{Type: ProviderSPIFFE, Priority: 0, Enabled: true},
		{Type: ProviderK8sSA, Priority: 1, Issuer: "https://k8s.example.com", Enabled: true},
	}
	v := NewValidator(configs, l)
	if v.spiffe == nil {
		t.Error("expected SPIFFE verifier to be registered")
	}
}

func TestNewValidator_NoCertProviders(t *testing.T) {
	l := newTestLogger()
	v := NewValidator([]ProviderConfig{}, l)
	_, err := v.ValidateCert(nil)
	if err == nil {
		t.Error("expected error when no SPIFFE verifier configured")
	}
}

func TestNewValidator_NoTokenProviders(t *testing.T) {
	l := newTestLogger()
	v := NewValidator([]ProviderConfig{}, l)
	ctx := context.Background()
	_, err := v.ValidateToken(ctx, "any-token")
	if err == nil {
		t.Error("expected error when no token providers configured")
	}
}

func TestNewValidator_EmptyConfig(t *testing.T) {
	l := newTestLogger()
	v := NewValidator(nil, l)
	if v == nil {
		t.Fatal("expected non-nil validator from empty config")
	}
}

// ---------------------------------------------------------------------------
// ValidatePeer
// ---------------------------------------------------------------------------

func TestValidatePeer_EmptyTokenAndNoCerts(t *testing.T) {
	l := newTestLogger()
	v := NewValidator([]ProviderConfig{}, l)
	ctx := context.Background()
	_, err := v.ValidatePeer(ctx, nil, "")
	if err == nil {
		t.Error("expected error when no token and no certs provided")
	}
}

func TestValidatePeer_EmptyCertsNoToken(t *testing.T) {
	l := newTestLogger()
	v := NewValidator([]ProviderConfig{}, l)
	ctx := context.Background()
	_, err := v.ValidatePeer(ctx, nil, "")
	if err == nil {
		t.Error("expected identity validation error with no providers")
	}
}

// ---------------------------------------------------------------------------
// SPIFFEVerifier
// ---------------------------------------------------------------------------

func TestSPIFFEVerifier_TokenAlwaysErrors(t *testing.T) {
	cfg := ProviderConfig{Type: ProviderSPIFFE, Enabled: true}
	sv := newSPIFFEVerifier(cfg)
	ctx := context.Background()
	_, err := sv.Verify(ctx, "any-token")
	if err == nil {
		t.Error("expected error for token-based SPIFFE verification (cert-only verifier)")
	}
}

func TestSPIFFEVerifier_EmptyCerts(t *testing.T) {
	cfg := ProviderConfig{Type: ProviderSPIFFE, Enabled: true}
	sv := newSPIFFEVerifier(cfg)
	_, err := sv.VerifyCert(nil)
	if err == nil {
		t.Error("expected error for nil cert slice")
	}
}

func TestSPIFFEVerifier_EmptyCertsExplicit(t *testing.T) {
	// Pass a typed nil to exercise the same "no certificates provided" guard.
	cfg := ProviderConfig{Type: ProviderSPIFFE, Enabled: true}
	sv := newSPIFFEVerifier(cfg)
	_, err := sv.VerifyCert(nil)
	if err == nil {
		t.Error("expected error for nil cert list")
	}
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

func TestClaimString_FirstKeyWins(t *testing.T) {
	claims := map[string]interface{}{
		"a": "value-a",
		"b": "value-b",
	}
	result := claimString(claims, "a", "b")
	if result != "value-a" {
		t.Errorf("expected value-a, got %q", result)
	}
}

func TestClaimString_FallsBackToSecondKey(t *testing.T) {
	claims := map[string]interface{}{
		"b": "value-b",
	}
	result := claimString(claims, "a", "b")
	if result != "value-b" {
		t.Errorf("expected value-b, got %q", result)
	}
}

func TestClaimString_MissingAllKeys(t *testing.T) {
	claims := map[string]interface{}{}
	result := claimString(claims, "a", "b", "c")
	if result != "" {
		t.Errorf("expected empty string, got %q", result)
	}
}

func TestClaimString_NonStringValue(t *testing.T) {
	claims := map[string]interface{}{
		"count": 42,
	}
	result := claimString(claims, "count")
	if result != "" {
		t.Errorf("expected empty string for non-string value, got %q", result)
	}
}

func TestClaimString_EmptyStringSkipped(t *testing.T) {
	// An empty string value should be skipped and the next key tried.
	claims := map[string]interface{}{
		"a": "",
		"b": "fallback",
	}
	result := claimString(claims, "a", "b")
	if result != "fallback" {
		t.Errorf("expected fallback, got %q", result)
	}
}

func TestSafeString_String(t *testing.T) {
	if safeString("hello") != "hello" {
		t.Error("expected 'hello'")
	}
}

func TestSafeString_Nil(t *testing.T) {
	if safeString(nil) != "" {
		t.Error("expected empty string for nil")
	}
}

func TestSafeString_Int(t *testing.T) {
	if safeString(42) != "" {
		t.Error("expected empty string for non-string value")
	}
}

func TestSafeString_EmptyString(t *testing.T) {
	if safeString("") != "" {
		t.Error("expected empty string")
	}
}
