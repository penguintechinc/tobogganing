// Package identity provides unified workload identity validation for the hub-router.
//
// Multiple identity attestation mechanisms are tried in priority order:
//
//  1. Cloud-native providers (EKS Pod Identity, GCP Workload Identity, Azure WI)
//     via standard OIDC — highest priority.
//  2. SPIFFE/SPIRE SVIDs via X.509 certificate chain — fallback for on-prem.
//  3. Kubernetes ServiceAccount tokens via OIDC discovery — lowest priority.
//
// A validated identity is returned as a WorkloadID that downstream policy
// evaluation (see package policy) can consume directly.
package identity

import (
	"context"
	"crypto/x509"
	"fmt"
	"net/url"
	"sort"
	"strings"
	"sync"

	"github.com/coreos/go-oidc/v3/oidc"
	log "github.com/sirupsen/logrus"
)

// ProviderType identifies the identity attestation mechanism used for a
// particular WorkloadID.
type ProviderType string

const (
	ProviderEKSPodIdentity  ProviderType = "eks_pod_identity"
	ProviderGCPWorkloadID   ProviderType = "gcp_wi"
	ProviderAzureWorkloadID ProviderType = "azure_wi"
	ProviderSPIFFE          ProviderType = "spiffe"
	ProviderK8sSA           ProviderType = "k8s_sa"
)

// WorkloadID represents a verified workload identity resolved from any
// supported provider.  Fields that are not available for a given provider
// are left as empty strings.
type WorkloadID struct {
	Subject   string       `json:"subject"`
	Issuer    string       `json:"issuer"`
	Provider  ProviderType `json:"provider"`
	Tenant    string       `json:"tenant"`
	Cluster   string       `json:"cluster"`
	Namespace string       `json:"namespace"`
	Service   string       `json:"service"`
	// SpiffeID is populated only when Provider == ProviderSPIFFE.
	SpiffeID  string                 `json:"spiffe_id,omitempty"`
	RawClaims map[string]interface{} `json:"raw_claims,omitempty"`
}

// ProviderConfig holds the configuration for a single identity provider.
// Lower Priority values are tried first (0 = highest priority).
type ProviderConfig struct {
	Type     ProviderType
	Priority int
	Issuer   string
	Audience string
	Enabled  bool
}

// tokenVerifier is the internal interface implemented by each provider
// backend.  Only ValidateToken callers need token-based verification;
// SPIFFE uses ValidateCert instead.
type tokenVerifier interface {
	Verify(ctx context.Context, token string) (*WorkloadID, error)
}

// providerEntry couples a ProviderConfig with its runtime verifier.
type providerEntry struct {
	config   ProviderConfig
	verifier tokenVerifier
}

// Validator tries each configured provider in priority order to validate
// workload identity from either bearer tokens or X.509 certificate chains.
// It is safe to use concurrently; the provider list is protected by a
// read/write mutex.
type Validator struct {
	providers []providerEntry
	spiffe    *SPIFFEVerifier
	mu        sync.RWMutex
	logger    *log.Entry
}

// NewValidator constructs a Validator from the supplied provider configs.
// Disabled providers are ignored.  Providers are sorted ascending by
// Priority so that lower-numbered providers are tried first.
func NewValidator(configs []ProviderConfig, logger *log.Logger) *Validator {
	v := &Validator{
		logger: logger.WithField("component", "identity.validator"),
	}

	// Sort configs by priority before building entries so the slice order
	// matches evaluation order.
	sorted := make([]ProviderConfig, len(configs))
	copy(sorted, configs)
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].Priority < sorted[j].Priority
	})

	for _, cfg := range sorted {
		if !cfg.Enabled {
			v.logger.Debugf("provider %s disabled, skipping", cfg.Type)
			continue
		}

		switch cfg.Type {
		case ProviderEKSPodIdentity, ProviderGCPWorkloadID, ProviderAzureWorkloadID:
			verifier := newCloudNativeVerifier(cfg, logger)
			v.providers = append(v.providers, providerEntry{config: cfg, verifier: verifier})
			v.logger.Infof("registered cloud-native provider %s (priority %d)", cfg.Type, cfg.Priority)

		case ProviderSPIFFE:
			// SPIFFE uses certificate validation, not tokens.  Store a dedicated
			// verifier but do not register it in the token-based providers slice.
			v.spiffe = newSPIFFEVerifier(cfg)
			v.logger.Infof("registered SPIFFE verifier (priority %d)", cfg.Priority)

		case ProviderK8sSA:
			verifier := newK8sSAVerifier(cfg, logger)
			v.providers = append(v.providers, providerEntry{config: cfg, verifier: verifier})
			v.logger.Infof("registered K8s SA provider (priority %d)", cfg.Priority)

		default:
			v.logger.Warnf("unknown provider type %q, skipping", cfg.Type)
		}
	}

	return v
}

// ValidateToken attempts to verify a bearer token against each enabled
// token-based provider in priority order.  The first successful result is
// returned.  An error is returned only when every provider rejects the token.
func (v *Validator) ValidateToken(ctx context.Context, token string) (*WorkloadID, error) {
	v.mu.RLock()
	providers := v.providers
	v.mu.RUnlock()

	var lastErr error
	for _, entry := range providers {
		id, err := entry.verifier.Verify(ctx, token)
		if err == nil {
			v.logger.Debugf("token accepted by provider %s subject=%s", entry.config.Type, id.Subject)
			return id, nil
		}
		v.logger.Debugf("provider %s rejected token: %v", entry.config.Type, err)
		lastErr = err
	}

	if lastErr != nil {
		return nil, fmt.Errorf("all providers rejected token: %w", lastErr)
	}
	return nil, fmt.Errorf("no token providers configured")
}

// ValidateCert attempts to verify a peer certificate chain using the SPIFFE
// verifier.  If no SPIFFE verifier is configured an error is returned.
func (v *Validator) ValidateCert(certs []*x509.Certificate) (*WorkloadID, error) {
	v.mu.RLock()
	spiffe := v.spiffe
	v.mu.RUnlock()

	if spiffe == nil {
		return nil, fmt.Errorf("no SPIFFE verifier configured")
	}
	return spiffe.VerifyCert(certs)
}

// ValidatePeer is the primary entry point for mTLS peers that may present
// both a token and a certificate chain.  Token verification is attempted
// first (if token is non-empty) across all token providers in priority order,
// then certificate validation via the SPIFFE verifier.  Returns the first
// successful WorkloadID.
func (v *Validator) ValidatePeer(ctx context.Context, certs []*x509.Certificate, token string) (*WorkloadID, error) {
	if token != "" {
		id, err := v.ValidateToken(ctx, token)
		if err == nil {
			return id, nil
		}
		v.logger.Debugf("token validation failed for peer, trying cert: %v", err)
	}

	if len(certs) > 0 {
		id, err := v.ValidateCert(certs)
		if err == nil {
			return id, nil
		}
		v.logger.Debugf("cert validation failed for peer: %v", err)
	}

	return nil, fmt.Errorf("identity validation failed: no valid token or certificate presented")
}

// ---------------------------------------------------------------------------
// CloudNativeVerifier — OIDC token validation for EKS / GCP / Azure
// ---------------------------------------------------------------------------

// CloudNativeVerifier validates OIDC bearer tokens emitted by cloud-native
// workload identity providers (EKS Pod Identity, GCP WI, Azure WI).
// All three providers conform to standard OIDC so a single implementation
// covers all of them.
type CloudNativeVerifier struct {
	config   ProviderConfig
	verifier *oidc.IDTokenVerifier
	logger   *log.Logger
}

func newCloudNativeVerifier(cfg ProviderConfig, logger *log.Logger) *CloudNativeVerifier {
	return &CloudNativeVerifier{
		config: cfg,
		logger: logger,
		// The oidc.IDTokenVerifier is created lazily on the first Verify call
		// because NewProvider requires an HTTP round-trip (OIDC discovery).
	}
}

// Verify validates token using OIDC discovery against the configured issuer.
// Claims are mapped to a WorkloadID; cloud-provider-specific claim names are
// handled with best-effort mapping.
func (c *CloudNativeVerifier) Verify(ctx context.Context, token string) (*WorkloadID, error) {
	verifier, err := c.getVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("cloud-native verifier (%s): setup failed: %w", c.config.Type, err)
	}

	idToken, err := verifier.Verify(ctx, token)
	if err != nil {
		return nil, fmt.Errorf("cloud-native verifier (%s): token invalid: %w", c.config.Type, err)
	}

	var claims map[string]interface{}
	if err := idToken.Claims(&claims); err != nil {
		return nil, fmt.Errorf("cloud-native verifier (%s): failed to extract claims: %w", c.config.Type, err)
	}

	id := &WorkloadID{
		Subject:   idToken.Subject,
		Issuer:    idToken.Issuer,
		Provider:  c.config.Type,
		RawClaims: claims,
	}

	// Map well-known claim fields to WorkloadID, covering the different
	// naming conventions used by each cloud provider.
	id.Namespace = claimString(claims, "kubernetes.io/namespace", "namespace", "k8s-namespace")
	id.Service = claimString(claims, "kubernetes.io/serviceaccount/name", "service-account", "service_account", "service")
	id.Cluster = claimString(claims, "cluster_name", "cluster", "kubernetes.io/cluster")
	id.Tenant = claimString(claims, "tenant_id", "tenant", "account_id", "project_id", "subscription_id")

	return id, nil
}

// getVerifier returns the cached IDTokenVerifier or creates it via OIDC
// discovery.  No internal locking is needed here — worst case two goroutines
// both create a verifier; the later one is simply discarded.
func (c *CloudNativeVerifier) getVerifier(ctx context.Context) (*oidc.IDTokenVerifier, error) {
	if c.verifier != nil {
		return c.verifier, nil
	}

	provider, err := oidc.NewProvider(ctx, c.config.Issuer)
	if err != nil {
		return nil, fmt.Errorf("OIDC discovery for %s failed: %w", c.config.Issuer, err)
	}

	oidcConfig := &oidc.Config{}
	if c.config.Audience != "" {
		oidcConfig.ClientID = c.config.Audience
	} else {
		oidcConfig.SkipClientIDCheck = true
	}

	c.verifier = provider.Verifier(oidcConfig)
	return c.verifier, nil
}

// ---------------------------------------------------------------------------
// SPIFFEVerifier — X.509 SVID certificate validation
// ---------------------------------------------------------------------------

// SPIFFEVerifier validates SPIFFE SVIDs presented as X.509 certificate chains.
// It holds a configurable trusted CA bundle and parses SPIFFE IDs from the
// SubjectAlternativeName URI extension.
type SPIFFEVerifier struct {
	config  ProviderConfig
	certPool *x509.CertPool
}

func newSPIFFEVerifier(cfg ProviderConfig) *SPIFFEVerifier {
	return &SPIFFEVerifier{
		config:   cfg,
		certPool: x509.NewCertPool(),
	}
}

// AddTrustedCA adds a PEM-encoded CA certificate to the trusted bundle.
// This must be called before VerifyCert to establish chain-of-trust.
func (s *SPIFFEVerifier) AddTrustedCA(cert *x509.Certificate) {
	s.certPool.AddCert(cert)
}

// VerifyCert validates the supplied certificate chain and extracts the
// SPIFFE ID from the leaf certificate's SAN URI field.
func (s *SPIFFEVerifier) VerifyCert(certs []*x509.Certificate) (*WorkloadID, error) {
	if len(certs) == 0 {
		return nil, fmt.Errorf("SPIFFE verifier: no certificates provided")
	}

	leaf := certs[0]

	// Build intermediates pool from all certs except the leaf.
	intermediates := x509.NewCertPool()
	for _, c := range certs[1:] {
		intermediates.AddCert(c)
	}

	opts := x509.VerifyOptions{
		Roots:         s.certPool,
		Intermediates: intermediates,
	}

	if _, err := leaf.Verify(opts); err != nil {
		return nil, fmt.Errorf("SPIFFE verifier: certificate chain verification failed: %w", err)
	}

	// Extract the SPIFFE ID from SAN URIs.
	spiffeID, err := extractSPIFFEIDFromCert(leaf)
	if err != nil {
		return nil, fmt.Errorf("SPIFFE verifier: %w", err)
	}

	trustDomain, cluster, namespace, service, err := ParseSPIFFEID(spiffeID)
	if err != nil {
		return nil, fmt.Errorf("SPIFFE verifier: %w", err)
	}

	return &WorkloadID{
		Subject:   leaf.Subject.CommonName,
		Issuer:    leaf.Issuer.CommonName,
		Provider:  ProviderSPIFFE,
		Tenant:    trustDomain,
		Cluster:   cluster,
		Namespace: namespace,
		Service:   service,
		SpiffeID:  spiffeID,
	}, nil
}

// Verify implements tokenVerifier so that SPIFFEVerifier can be stored
// alongside token-based verifiers.  Token-based SPIFFE validation is not
// supported; callers should use VerifyCert instead.
func (s *SPIFFEVerifier) Verify(_ context.Context, _ string) (*WorkloadID, error) {
	return nil, fmt.Errorf("SPIFFE verifier: token-based validation is not supported; use VerifyCert")
}

// extractSPIFFEIDFromCert returns the first URI SAN that starts with
// "spiffe://".  An error is returned if no SPIFFE URI SAN is present.
func extractSPIFFEIDFromCert(cert *x509.Certificate) (string, error) {
	for _, uri := range cert.URIs {
		if uri != nil && strings.HasPrefix(uri.String(), "spiffe://") {
			return uri.String(), nil
		}
	}
	return "", fmt.Errorf("no SPIFFE ID found in certificate SAN URIs")
}

// ---------------------------------------------------------------------------
// K8sSAVerifier — Kubernetes ServiceAccount token validation
// ---------------------------------------------------------------------------

// K8sSAVerifier validates Kubernetes projected ServiceAccount tokens using
// OIDC discovery against the Kubernetes API server's issuer URL.
type K8sSAVerifier struct {
	config   ProviderConfig
	verifier *oidc.IDTokenVerifier
	logger   *log.Logger
}

func newK8sSAVerifier(cfg ProviderConfig, logger *log.Logger) *K8sSAVerifier {
	return &K8sSAVerifier{
		config: cfg,
		logger: logger,
	}
}

// Verify validates a Kubernetes ServiceAccount projected token using the
// configured OIDC issuer (typically the K8s API server URL with OIDC
// discovery enabled).
func (k *K8sSAVerifier) Verify(ctx context.Context, token string) (*WorkloadID, error) {
	verifier, err := k.getVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("k8s SA verifier: setup failed: %w", err)
	}

	idToken, err := verifier.Verify(ctx, token)
	if err != nil {
		return nil, fmt.Errorf("k8s SA verifier: token invalid: %w", err)
	}

	var claims map[string]interface{}
	if err := idToken.Claims(&claims); err != nil {
		return nil, fmt.Errorf("k8s SA verifier: failed to extract claims: %w", err)
	}

	id := &WorkloadID{
		Subject:   idToken.Subject,
		Issuer:    idToken.Issuer,
		Provider:  ProviderK8sSA,
		RawClaims: claims,
	}

	// Kubernetes projected SA tokens embed namespace and service account name
	// under the "kubernetes.io" claim namespace.
	if k8sClaims, ok := claims["kubernetes.io"].(map[string]interface{}); ok {
		id.Namespace = safeString(k8sClaims["namespace"])
		if sa, ok := k8sClaims["serviceaccount"].(map[string]interface{}); ok {
			id.Service = safeString(sa["name"])
		}
	}

	// Fall back to top-level claims if the nested form is absent.
	if id.Namespace == "" {
		id.Namespace = claimString(claims, "namespace", "k8s-namespace")
	}
	if id.Service == "" {
		id.Service = claimString(claims, "service_account", "serviceaccount")
	}

	return id, nil
}

func (k *K8sSAVerifier) getVerifier(ctx context.Context) (*oidc.IDTokenVerifier, error) {
	if k.verifier != nil {
		return k.verifier, nil
	}

	provider, err := oidc.NewProvider(ctx, k.config.Issuer)
	if err != nil {
		return nil, fmt.Errorf("OIDC discovery for K8s issuer %s failed: %w", k.config.Issuer, err)
	}

	oidcConfig := &oidc.Config{}
	if k.config.Audience != "" {
		oidcConfig.ClientID = k.config.Audience
	} else {
		oidcConfig.SkipClientIDCheck = true
	}

	k.verifier = provider.Verifier(oidcConfig)
	return k.verifier, nil
}

// ---------------------------------------------------------------------------
// ParseSPIFFEID
// ---------------------------------------------------------------------------

// ParseSPIFFEID parses a SPIFFE ID URI into its constituent parts.
//
// Expected format: spiffe://<trust-domain>/<cluster>/<namespace>/<service>
//
// Returns an error if the URI is not a valid SPIFFE ID or does not contain
// the expected four path segments.
func ParseSPIFFEID(spiffeID string) (trustDomain, cluster, namespace, service string, err error) {
	parsed, parseErr := url.Parse(spiffeID)
	if parseErr != nil {
		return "", "", "", "", fmt.Errorf("invalid SPIFFE ID URI %q: %w", spiffeID, parseErr)
	}

	if parsed.Scheme != "spiffe" {
		return "", "", "", "", fmt.Errorf("invalid SPIFFE ID %q: scheme must be 'spiffe', got %q", spiffeID, parsed.Scheme)
	}

	trustDomain = parsed.Host
	if trustDomain == "" {
		return "", "", "", "", fmt.Errorf("invalid SPIFFE ID %q: trust domain is empty", spiffeID)
	}

	// path begins with a leading slash; trim it before splitting.
	rawPath := strings.TrimPrefix(parsed.Path, "/")
	if rawPath == "" {
		return "", "", "", "", fmt.Errorf("SPIFFE ID %q has no path segments; expected <cluster>/<namespace>/<service>", spiffeID)
	}

	parts := strings.SplitN(rawPath, "/", 3)
	if len(parts) != 3 {
		return "", "", "", "", fmt.Errorf(
			"SPIFFE ID %q path must contain exactly three segments (<cluster>/<namespace>/<service>), got %d",
			spiffeID, len(parts),
		)
	}

	cluster = parts[0]
	namespace = parts[1]
	service = parts[2]

	if cluster == "" || namespace == "" || service == "" {
		return "", "", "", "", fmt.Errorf("SPIFFE ID %q contains empty path segments", spiffeID)
	}

	return trustDomain, cluster, namespace, service, nil
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

// claimString returns the string value of the first key found in claims.
// Returns an empty string when none of the keys are present or the value is
// not a string.
func claimString(claims map[string]interface{}, keys ...string) string {
	for _, k := range keys {
		if v, ok := claims[k]; ok {
			if s, ok := v.(string); ok && s != "" {
				return s
			}
		}
	}
	return ""
}

// safeString converts an interface{} value to a string, returning an empty
// string for non-string or nil values.
func safeString(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
