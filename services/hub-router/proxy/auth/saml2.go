package auth

import (
	"crypto/x509"
	"encoding/base64"
	"encoding/xml"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/beevik/etree"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	dsig "github.com/russellhaering/goxmldsig"
	log "github.com/sirupsen/logrus"
)

// samlACSURL is the Assertion Consumer Service URL this proxy advertises to
// the IdP and the value every accepted assertion's SubjectConfirmationData
// Recipient must match. Shared by the AuthnRequest builder and the response
// validator so the two can never drift apart.
const samlACSURL = "https://localhost:8443/auth/callback"

// samlAssertionTTLCleanupSlack bounds how long a consumed assertion ID is
// retained in the replay cache past its own NotOnOrAfter, purely so cleanup
// doesn't race a request that's still mid-validation at the expiry boundary.
const samlAssertionTTLCleanupSlack = 30 * time.Second

type SAML2Provider struct {
	idpMetadataURL    string
	spEntityID        string
	metadata          *IDPMetadata
	sessionSigningKey []byte

	replayMu       sync.Mutex
	usedAssertions map[string]time.Time
}

type IDPMetadata struct {
	EntityID            string `xml:"entityID,attr"`
	SingleSignOnService struct {
		Binding  string `xml:"Binding,attr"`
		Location string `xml:"Location,attr"`
	} `xml:"IDPSSODescriptor>SingleSignOnService"`
	Certificate string `xml:"IDPSSODescriptor>KeyDescriptor>KeyInfo>X509Data>X509Certificate"`
}

// samlAssertionClaims holds the fields extracted directly from the
// cryptographically validated <Assertion> subtree. Every field here MUST be
// read from the etree.Element returned by dsig.ValidationContext.Validate —
// never from an independent re-parse of the raw response — or a classic XML
// Signature Wrapping (XSW) attack can smuggle unsigned attacker-controlled
// claims past a check that only validated a signature elsewhere in the doc.
type samlAssertionClaims struct {
	assertionID      string
	nameID           string
	email            string
	name             string
	groups           []string
	audience         string
	notBefore        time.Time
	notOnOrAfter     time.Time
	confNotOnOrAfter time.Time
	recipient        string
	inResponseTo     string
}

// NewSAML2Provider constructs a SAML2 auth provider. sessionSigningKey is a
// dedicated, high-entropy server secret used exclusively to sign and verify
// the proxy's own session JWT — it must never be the SP entity ID, which is
// public (present in every AuthnRequest and IdP metadata exchange) and would
// let anyone forge a valid session token with arbitrary claims.
func NewSAML2Provider(idpMetadataURL, spEntityID, sessionSigningKey string) (*SAML2Provider, error) {
	signingKey, err := validateSessionSigningKey(sessionSigningKey)
	if err != nil {
		return nil, fmt.Errorf("saml2 provider: %w", err)
	}

	provider := &SAML2Provider{
		idpMetadataURL:    idpMetadataURL,
		spEntityID:        spEntityID,
		sessionSigningKey: signingKey,
		usedAssertions:    make(map[string]time.Time),
	}

	if err := provider.loadMetadata(); err != nil {
		return nil, err
	}

	return provider, nil
}

func (p *SAML2Provider) loadMetadata() error {
	resp, err := http.Get(p.idpMetadataURL)
	if err != nil {
		return fmt.Errorf("failed to fetch IDP metadata: %w", err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Warnf("Failed to close response body: %v", err)
		}
	}()

	var metadata IDPMetadata
	if err := xml.NewDecoder(resp.Body).Decode(&metadata); err != nil {
		return fmt.Errorf("failed to parse IDP metadata: %w", err)
	}

	p.metadata = &metadata
	return nil
}

func (p *SAML2Provider) LoginHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		requestID := fmt.Sprintf("_%s", generateState())
		// Single-use, short-lived correlation cookie: binds the eventual
		// CallbackHandler response to a login this proxy actually initiated,
		// and its ID doubles as the value the assertion's InResponseTo must
		// match — the core defense against a captured/replayed IdP response.
		c.SetCookie("saml_request_id", requestID, 300, "/", "", true, true)

		authRequest := p.generateAuthRequest(requestID)

		encoded := base64.StdEncoding.EncodeToString([]byte(authRequest))
		redirectURL := fmt.Sprintf("%s?SAMLRequest=%s", p.metadata.SingleSignOnService.Location, encoded)

		c.Redirect(http.StatusTemporaryRedirect, redirectURL)
	}
}

func (p *SAML2Provider) CallbackHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		samlResponse := c.PostForm("SAMLResponse")
		if samlResponse == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "no SAML response"})
			return
		}

		requestID, err := c.Cookie("saml_request_id")
		if err != nil || requestID == "" {
			log.Warn("SAML callback received with no matching login request")
			c.JSON(http.StatusUnauthorized, gin.H{"error": "no matching login request"})
			return
		}
		// Clear immediately, before validation: the correlation value is
		// single-use regardless of whether this attempt succeeds.
		c.SetCookie("saml_request_id", "", -1, "/", "", true, true)

		decoded, err := base64.StdEncoding.DecodeString(samlResponse)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid SAML response"})
			return
		}

		user, err := p.validateAndExtractUser(decoded, requestID, time.Now().UTC())
		if err != nil {
			log.Errorf("SAML assertion validation failed: %v", err)
			c.JSON(http.StatusUnauthorized, gin.H{"error": "SAML assertion validation failed"})
			return
		}

		// Create session token
		sessionToken := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"sub":    user.ID,
			"email":  user.Email,
			"name":   user.Name,
			"groups": user.Groups,
			"exp":    time.Now().Add(24 * time.Hour).Unix(),
		})

		tokenString, err := sessionToken.SignedString(p.sessionSigningKey)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create session"})
			return
		}

		c.SetCookie("session_token", tokenString, 86400, "/", "", true, true)
		c.Redirect(http.StatusTemporaryRedirect, "/")
	}
}

func (p *SAML2Provider) LogoutHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.SetCookie("session_token", "", -1, "/", "", true, true)

		// TODO: Implement SAML Single Logout
		c.JSON(http.StatusOK, gin.H{"message": "logged out"})
	}
}

func (p *SAML2Provider) ValidateToken(tokenString string) (*User, error) {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return p.sessionSigningKey, nil
	})

	if err != nil {
		return nil, err
	}

	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		groups := []string{}
		if g, ok := claims["groups"].([]interface{}); ok {
			for _, group := range g {
				if s, ok := group.(string); ok {
					groups = append(groups, s)
				}
			}
		}

		return &User{
			ID:     claims["sub"].(string),
			Email:  claims["email"].(string),
			Name:   claims["name"].(string),
			Groups: groups,
		}, nil
	}

	return nil, fmt.Errorf("invalid token")
}

func (p *SAML2Provider) GetUser(c *gin.Context) (*User, error) {
	cookie, err := c.Cookie("session_token")
	if err != nil {
		return nil, fmt.Errorf("no authentication found")
	}

	return p.ValidateToken(cookie)
}

func (p *SAML2Provider) generateAuthRequest(requestID string) string {
	issueInstant := time.Now().UTC().Format(time.RFC3339)

	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="%s"
    Version="2.0"
    IssueInstant="%s"
    Destination="%s"
    AssertionConsumerServiceURL="%s"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>%s</saml:Issuer>
</samlp:AuthnRequest>`, requestID, issueInstant, p.metadata.SingleSignOnService.Location, samlACSURL, p.spEntityID)
}

// validateAndExtractUser is the sole entry point for turning a raw (decoded)
// SAML response into a trusted *User. It enforces, in order: XML-DSig
// signature validation against the IdP metadata certificate, Audience,
// Conditions/SubjectConfirmationData time bounds, Recipient, InResponseTo
// binding to this proxy's own login attempt, and single-use replay
// protection — a forged, expired, mis-audienced, or replayed assertion is
// rejected before any claim is trusted.
func (p *SAML2Provider) validateAndExtractUser(raw []byte, requestID string, now time.Time) (*User, error) {
	validated, err := p.verifySignedElement(raw)
	if err != nil {
		return nil, err
	}

	assertionEl, err := extractAssertionElement(validated)
	if err != nil {
		return nil, err
	}

	claims, err := parseAssertionClaims(assertionEl)
	if err != nil {
		return nil, err
	}

	if claims.audience != p.spEntityID {
		return nil, fmt.Errorf("audience mismatch: expected %q got %q", p.spEntityID, claims.audience)
	}
	if !now.Before(claims.notOnOrAfter) {
		return nil, fmt.Errorf("assertion expired (Conditions NotOnOrAfter %s)", claims.notOnOrAfter)
	}
	if now.Before(claims.notBefore) {
		return nil, fmt.Errorf("assertion not yet valid (Conditions NotBefore %s)", claims.notBefore)
	}
	if !now.Before(claims.confNotOnOrAfter) {
		return nil, fmt.Errorf("assertion expired (SubjectConfirmationData NotOnOrAfter %s)", claims.confNotOnOrAfter)
	}
	if claims.recipient != samlACSURL {
		return nil, fmt.Errorf("recipient mismatch: expected %q got %q", samlACSURL, claims.recipient)
	}
	if claims.inResponseTo != requestID {
		return nil, fmt.Errorf("InResponseTo mismatch: this response does not match an in-flight login request")
	}

	if err := p.checkAndRecordReplay(claims.assertionID, claims.notOnOrAfter); err != nil {
		return nil, err
	}

	return &User{
		ID:     claims.nameID,
		Email:  claims.email,
		Name:   claims.name,
		Groups: claims.groups,
	}, nil
}

// verifySignedElement parses raw as XML and validates its enveloped XML-DSig
// signature against the configured IdP's metadata certificate. It returns
// the specific element the signature actually covers (the top-level
// <Response>, or an inner <Assertion> if only that is signed) — callers MUST
// extract all further claims from that returned element, never from a fresh
// parse of raw, to stay safe against XML Signature Wrapping.
func (p *SAML2Provider) verifySignedElement(raw []byte) (*etree.Element, error) {
	doc := etree.NewDocument()
	if err := doc.ReadFromBytes(raw); err != nil {
		return nil, fmt.Errorf("failed to parse SAML response XML: %w", err)
	}
	root := doc.Root()
	if root == nil {
		return nil, fmt.Errorf("empty SAML response document")
	}

	cert, err := p.idpCertificate()
	if err != nil {
		return nil, fmt.Errorf("failed to load IDP signing certificate: %w", err)
	}

	signedEl := findSignedElement(root)
	if signedEl == nil {
		return nil, fmt.Errorf("SAML response is not signed")
	}

	validationCtx := dsig.NewDefaultValidationContext(&dsig.MemoryX509CertificateStore{
		Roots: []*x509.Certificate{cert},
	})

	validated, err := validationCtx.Validate(signedEl)
	if err != nil {
		return nil, fmt.Errorf("SAML signature validation failed: %w", err)
	}

	return validated, nil
}

// findSignedElement returns the element the response's enveloped signature
// covers: the response root itself if it carries a direct <Signature> child,
// otherwise the first descendant <Assertion> that carries one. Returns nil
// if nothing in the document is signed at all.
func findSignedElement(root *etree.Element) *etree.Element {
	if root.FindElement("./Signature") != nil {
		return root
	}
	for _, assertion := range root.FindElements(".//Assertion") {
		if assertion.FindElement("./Signature") != nil {
			return assertion
		}
	}
	return nil
}

// extractAssertionElement resolves the <Assertion> element within a
// validated signature scope. If the whole <Response> was signed, the
// assertion is a descendant still covered by that signature; if only the
// assertion itself was signed, validated IS the assertion.
func extractAssertionElement(validated *etree.Element) (*etree.Element, error) {
	if validated.Tag == "Assertion" {
		return validated, nil
	}
	assertion := validated.FindElement(".//Assertion")
	if assertion == nil {
		return nil, fmt.Errorf("no Assertion found within the signed content")
	}
	return assertion, nil
}

// idpCertificate parses the IdP's signing certificate out of the metadata
// fetched at startup (base64-encoded DER, per the SAML metadata schema).
func (p *SAML2Provider) idpCertificate() (*x509.Certificate, error) {
	if p.metadata == nil || strings.TrimSpace(p.metadata.Certificate) == "" {
		return nil, fmt.Errorf("no IDP signing certificate available in metadata")
	}

	certData := strings.Join(strings.Fields(p.metadata.Certificate), "")
	der, err := base64.StdEncoding.DecodeString(certData)
	if err != nil {
		return nil, fmt.Errorf("failed to decode IDP certificate: %w", err)
	}

	cert, err := x509.ParseCertificate(der)
	if err != nil {
		return nil, fmt.Errorf("failed to parse IDP certificate: %w", err)
	}

	return cert, nil
}

// parseAssertionClaims reads every security-relevant field directly off the
// signature-validated <Assertion> element. All required fields (ID, NameID,
// SubjectConfirmationData bounds, Conditions bounds, Audience) must be
// present — a spec-incomplete assertion is rejected rather than treated as
// "unbounded" / implicitly trusted.
func parseAssertionClaims(assertion *etree.Element) (samlAssertionClaims, error) {
	var claims samlAssertionClaims

	claims.assertionID = assertion.SelectAttrValue("ID", "")
	if claims.assertionID == "" {
		return claims, fmt.Errorf("assertion missing ID attribute")
	}

	nameID := assertion.FindElement("./Subject/NameID")
	if nameID == nil || strings.TrimSpace(nameID.Text()) == "" {
		return claims, fmt.Errorf("assertion missing Subject/NameID")
	}
	claims.nameID = strings.TrimSpace(nameID.Text())
	claims.email = claims.nameID

	confData := assertion.FindElement("./Subject/SubjectConfirmation/SubjectConfirmationData")
	if confData == nil {
		return claims, fmt.Errorf("assertion missing SubjectConfirmationData")
	}
	claims.recipient = confData.SelectAttrValue("Recipient", "")
	claims.inResponseTo = confData.SelectAttrValue("InResponseTo", "")

	confNotOnOrAfterStr := confData.SelectAttrValue("NotOnOrAfter", "")
	if confNotOnOrAfterStr == "" {
		return claims, fmt.Errorf("assertion missing SubjectConfirmationData NotOnOrAfter")
	}
	t, err := time.Parse(time.RFC3339, confNotOnOrAfterStr)
	if err != nil {
		return claims, fmt.Errorf("invalid SubjectConfirmationData NotOnOrAfter: %w", err)
	}
	claims.confNotOnOrAfter = t

	conditions := assertion.FindElement("./Conditions")
	if conditions == nil {
		return claims, fmt.Errorf("assertion missing Conditions")
	}
	notBeforeStr := conditions.SelectAttrValue("NotBefore", "")
	notOnOrAfterStr := conditions.SelectAttrValue("NotOnOrAfter", "")
	if notBeforeStr == "" || notOnOrAfterStr == "" {
		return claims, fmt.Errorf("assertion Conditions missing NotBefore/NotOnOrAfter")
	}
	if claims.notBefore, err = time.Parse(time.RFC3339, notBeforeStr); err != nil {
		return claims, fmt.Errorf("invalid Conditions NotBefore: %w", err)
	}
	if claims.notOnOrAfter, err = time.Parse(time.RFC3339, notOnOrAfterStr); err != nil {
		return claims, fmt.Errorf("invalid Conditions NotOnOrAfter: %w", err)
	}

	audience := conditions.FindElement("./AudienceRestriction/Audience")
	if audience == nil || strings.TrimSpace(audience.Text()) == "" {
		return claims, fmt.Errorf("assertion Conditions missing AudienceRestriction/Audience")
	}
	claims.audience = strings.TrimSpace(audience.Text())

	for _, attr := range assertion.FindElements("./AttributeStatement/Attribute") {
		name := attr.SelectAttrValue("Name", "")
		var values []string
		for _, v := range attr.FindElements("./AttributeValue") {
			values = append(values, strings.TrimSpace(v.Text()))
		}
		switch name {
		case "email", "mail":
			if len(values) > 0 {
				claims.email = values[0]
			}
		case "name", "displayName":
			if len(values) > 0 {
				claims.name = values[0]
			}
		case "groups", "memberOf":
			claims.groups = values
		}
	}

	return claims, nil
}

// checkAndRecordReplay rejects an assertion ID that has already been
// consumed within its own validity window, and records this one so a
// captured/resubmitted copy of the same assertion is rejected on any
// subsequent attempt. Entries are purged lazily once their (already-checked)
// NotOnOrAfter has passed, bounding cache growth to in-flight logins.
func (p *SAML2Provider) checkAndRecordReplay(assertionID string, notOnOrAfter time.Time) error {
	p.replayMu.Lock()
	defer p.replayMu.Unlock()

	now := time.Now().UTC()
	for id, exp := range p.usedAssertions {
		if now.After(exp) {
			delete(p.usedAssertions, id)
		}
	}

	if exp, seen := p.usedAssertions[assertionID]; seen && now.Before(exp) {
		return fmt.Errorf("assertion %s has already been used (replay detected)", assertionID)
	}

	p.usedAssertions[assertionID] = notOnOrAfter.Add(samlAssertionTTLCleanupSlack)
	return nil
}
