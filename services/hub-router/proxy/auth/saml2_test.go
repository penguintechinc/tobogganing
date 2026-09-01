package auth

import (
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/beevik/etree"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	dsig "github.com/russellhaering/goxmldsig"
)

const testSPEntityID = "https://headend.example.com/sp"

// buildSignedSAMLResponse constructs a full <Response>/<Assertion> document,
// signs the assertion with a freshly generated test keypair (the same API a
// real SAML toolkit uses: dsig.NewDefaultSigningContext + SignEnveloped),
// and returns the serialized XML plus the DER-encoded certificate that
// verifies it — i.e. the same shape of material a provider's IdP metadata
// would supply.
func buildSignedSAMLResponse(t *testing.T, nameID, requestID string, notBefore, notOnOrAfter time.Time) (raw, certDER []byte) {
	t.Helper()

	doc := etree.NewDocument()
	response := doc.CreateElement("Response")
	response.CreateAttr("ID", "resp-"+requestID)

	assertion := response.CreateElement("Assertion")
	assertion.CreateAttr("ID", "assertion-"+requestID)

	subject := assertion.CreateElement("Subject")
	nameIDEl := subject.CreateElement("NameID")
	nameIDEl.SetText(nameID)

	subjConf := subject.CreateElement("SubjectConfirmation")
	subjConfData := subjConf.CreateElement("SubjectConfirmationData")
	subjConfData.CreateAttr("Recipient", samlACSURL)
	subjConfData.CreateAttr("InResponseTo", requestID)
	subjConfData.CreateAttr("NotOnOrAfter", notOnOrAfter.Format(time.RFC3339))

	conditions := assertion.CreateElement("Conditions")
	conditions.CreateAttr("NotBefore", notBefore.Format(time.RFC3339))
	conditions.CreateAttr("NotOnOrAfter", notOnOrAfter.Format(time.RFC3339))
	audienceRestriction := conditions.CreateElement("AudienceRestriction")
	audience := audienceRestriction.CreateElement("Audience")
	audience.SetText(testSPEntityID)

	attrStatement := assertion.CreateElement("AttributeStatement")
	emailAttr := attrStatement.CreateElement("Attribute")
	emailAttr.CreateAttr("Name", "email")
	emailVal := emailAttr.CreateElement("AttributeValue")
	emailVal.SetText(nameID)

	ks := dsig.RandomKeyStoreForTest()
	_, cert, err := ks.GetKeyPair()
	if err != nil {
		t.Fatalf("failed to obtain test keypair: %v", err)
	}

	signingCtx := dsig.NewDefaultSigningContext(ks)
	signedAssertion, err := signingCtx.SignEnveloped(assertion)
	if err != nil {
		t.Fatalf("failed to sign test assertion: %v", err)
	}

	response.RemoveChild(assertion)
	response.AddChild(signedAssertion)
	doc.SetRoot(response)

	rawBytes, err := doc.WriteToBytes()
	if err != nil {
		t.Fatalf("failed to serialize test SAML response: %v", err)
	}

	return rawBytes, cert
}

func newTestSAML2Provider(t *testing.T, certDER []byte) *SAML2Provider {
	t.Helper()
	return &SAML2Provider{
		spEntityID:        testSPEntityID,
		sessionSigningKey: []byte("real-high-entropy-session-signing-key-32bytes+"),
		usedAssertions:    make(map[string]time.Time),
		metadata: &IDPMetadata{
			Certificate: base64.StdEncoding.EncodeToString(certDER),
		},
	}
}

func TestSAML2_ValidAssertion_IsAccepted(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-1", now.Add(-time.Minute), now.Add(5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	user, err := p.validateAndExtractUser(raw, "req-1", now)
	if err != nil {
		t.Fatalf("expected valid signed assertion to be accepted, got error: %v", err)
	}
	if user.Email != "user@example.com" {
		t.Errorf("unexpected user email: %q", user.Email)
	}
}

func TestSAML2_UnsignedAssertion_IsRejected(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-2", now.Add(-time.Minute), now.Add(5*time.Minute))

	// Strip the <Signature> element out entirely to simulate an attacker
	// submitting an unsigned assertion.
	doc := etree.NewDocument()
	if err := doc.ReadFromBytes(raw); err != nil {
		t.Fatalf("failed to reparse test fixture: %v", err)
	}
	assertion := doc.Root().FindElement(".//Assertion")
	sig := assertion.FindElement("./Signature")
	if sig == nil {
		t.Fatal("test fixture is missing its own signature, cannot construct unsigned variant")
	}
	assertion.RemoveChild(sig)
	unsignedRaw, err := doc.WriteToBytes()
	if err != nil {
		t.Fatalf("failed to serialize unsigned fixture: %v", err)
	}

	p := newTestSAML2Provider(t, cert)

	if _, err := p.validateAndExtractUser(unsignedRaw, "req-2", now); err == nil {
		t.Fatal("expected unsigned assertion to be rejected, got no error")
	}
}

func TestSAML2_TamperedAssertion_IsRejected(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-3", now.Add(-time.Minute), now.Add(5*time.Minute))

	// Forge the assertion after signing: swap the NameID an attacker would
	// want to control (e.g. to impersonate an admin) while keeping the
	// original signature bytes — this must fail digest verification.
	tampered := strings.Replace(string(raw), "user@example.com", "admin@example.com", 1)

	p := newTestSAML2Provider(t, cert)

	if _, err := p.validateAndExtractUser([]byte(tampered), "req-3", now); err == nil {
		t.Fatal("expected tampered assertion to be rejected, got no error")
	}
}

func TestSAML2_WrongSigningKey_IsRejected(t *testing.T) {
	now := time.Now().UTC()
	raw, _ := buildSignedSAMLResponse(t, "user@example.com", "req-4", now.Add(-time.Minute), now.Add(5*time.Minute))

	// Trust a different (attacker-controlled) certificate than the one that
	// actually signed the assertion — must be rejected even though the
	// assertion's own embedded signature is internally well-formed.
	_, otherCert, err := dsig.RandomKeyStoreForTest().GetKeyPair()
	if err != nil {
		t.Fatalf("failed to obtain second test keypair: %v", err)
	}
	p := newTestSAML2Provider(t, otherCert)

	if _, err := p.validateAndExtractUser(raw, "req-4", now); err == nil {
		t.Fatal("expected assertion signed by an untrusted key to be rejected, got no error")
	}
}

func TestSAML2_ExpiredAssertion_IsRejected(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-5", now.Add(-10*time.Minute), now.Add(-5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	if _, err := p.validateAndExtractUser(raw, "req-5", now); err == nil {
		t.Fatal("expected expired assertion to be rejected, got no error")
	}
}

func TestSAML2_InResponseToMismatch_IsRejected(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-6", now.Add(-time.Minute), now.Add(5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	if _, err := p.validateAndExtractUser(raw, "some-other-request-id", now); err == nil {
		t.Fatal("expected InResponseTo mismatch to be rejected, got no error")
	}
}

func TestSAML2_ReplayedAssertion_IsRejectedOnSecondUse(t *testing.T) {
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-7", now.Add(-time.Minute), now.Add(5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	if _, err := p.validateAndExtractUser(raw, "req-7", now); err != nil {
		t.Fatalf("expected first use to succeed, got error: %v", err)
	}
	if _, err := p.validateAndExtractUser(raw, "req-7", now); err == nil {
		t.Fatal("expected replayed assertion to be rejected on second use, got no error")
	}
}

// --- Session-JWT forgery (CRITICAL 2a): the proxy session token itself ---

func TestSAML2SessionToken_RejectsForgeryWithSPEntityID(t *testing.T) {
	realSecret := "real-high-entropy-session-signing-key-32bytes+"
	p := &SAML2Provider{
		spEntityID:        testSPEntityID,
		sessionSigningKey: []byte(realSecret),
	}

	// Forge a token the way pre-fix code would have: signed with the PUBLIC
	// SP entity ID instead of a real server secret.
	forged := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":    "attacker",
		"email":  "attacker@example.com",
		"name":   "Attacker",
		"groups": []string{"admin"},
		"exp":    time.Now().Add(time.Hour).Unix(),
	})
	forgedString, err := forged.SignedString([]byte(p.spEntityID))
	if err != nil {
		t.Fatalf("failed to build forged token fixture: %v", err)
	}

	if _, err := p.ValidateToken(forgedString); err == nil {
		t.Fatal("expected forged token signed with public spEntityID to be rejected, got no error")
	}
}

func TestSAML2SessionToken_AcceptsRealServerSecret(t *testing.T) {
	realSecret := "real-high-entropy-session-signing-key-32bytes+"
	p := &SAML2Provider{
		spEntityID:        testSPEntityID,
		sessionSigningKey: []byte(realSecret),
	}

	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":    "user-1",
		"email":  "user@example.com",
		"name":   "User One",
		"groups": []string{"member"},
		"exp":    time.Now().Add(time.Hour).Unix(),
	})
	tokString, err := tok.SignedString(p.sessionSigningKey)
	if err != nil {
		t.Fatalf("failed to sign token with real secret: %v", err)
	}

	user, err := p.ValidateToken(tokString)
	if err != nil {
		t.Fatalf("expected token signed with real session secret to validate, got error: %v", err)
	}
	if user.ID != "user-1" || user.Email != "user@example.com" {
		t.Errorf("unexpected user claims: %+v", user)
	}
}

func TestNewSAML2Provider_FailsClosedWithoutSessionSigningKey(t *testing.T) {
	if _, err := NewSAML2Provider("https://idp.example.com/metadata", testSPEntityID, ""); err == nil {
		t.Fatal("expected error for empty session signing key")
	}
	if _, err := NewSAML2Provider("https://idp.example.com/metadata", testSPEntityID, "short"); err == nil {
		t.Fatal("expected error for too-short session signing key")
	}
}

// --- HTTP-level handler tests: exercise the real gin.HandlerFunc entry points ---

func TestSAML2LoginHandler_RequestIDCookieMatchesAuthnRequest(t *testing.T) {
	gin.SetMode(gin.TestMode)
	p := &SAML2Provider{spEntityID: testSPEntityID}
	p.metadata = &IDPMetadata{}
	p.metadata.SingleSignOnService.Location = "https://idp.example.com/sso"

	router := gin.New()
	router.GET("/auth/login", p.LoginHandler())

	req := httptest.NewRequest(http.MethodGet, "/auth/login", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusTemporaryRedirect {
		t.Fatalf("expected redirect, got %d", w.Code)
	}

	var cookieRequestID string
	for _, ck := range w.Result().Cookies() {
		if ck.Name == "saml_request_id" {
			cookieRequestID = ck.Value
		}
	}
	if cookieRequestID == "" {
		t.Fatal("expected saml_request_id cookie to be set")
	}

	loc, err := url.Parse(w.Header().Get("Location"))
	if err != nil {
		t.Fatalf("failed to parse redirect location: %v", err)
	}
	decoded, err := base64.StdEncoding.DecodeString(loc.Query().Get("SAMLRequest"))
	if err != nil {
		t.Fatalf("failed to decode SAMLRequest: %v", err)
	}
	if !strings.Contains(string(decoded), `ID="`+cookieRequestID+`"`) {
		t.Errorf("AuthnRequest ID does not match saml_request_id cookie %q: %s", cookieRequestID, decoded)
	}
}

func TestSAML2CallbackHandler_ValidResponse_SetsSessionCookieAndRedirects(t *testing.T) {
	gin.SetMode(gin.TestMode)
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-http-1", now.Add(-time.Minute), now.Add(5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	w := serveSAMLCallback(t, p, raw, "req-http-1")

	if w.Code != http.StatusTemporaryRedirect {
		t.Fatalf("expected redirect, got %d body=%s", w.Code, w.Body.String())
	}

	var sessionToken string
	for _, ck := range w.Result().Cookies() {
		if ck.Name == "session_token" {
			sessionToken = ck.Value
		}
	}
	if sessionToken == "" {
		t.Fatal("expected session_token cookie to be set")
	}

	user, err := p.ValidateToken(sessionToken)
	if err != nil {
		t.Fatalf("expected session token to validate, got error: %v", err)
	}
	if user.Email != "user@example.com" {
		t.Errorf("unexpected user email in session: %q", user.Email)
	}
}

func TestSAML2CallbackHandler_MissingRequestIDCookie_Rejected(t *testing.T) {
	gin.SetMode(gin.TestMode)
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-http-2", now.Add(-time.Minute), now.Add(5*time.Minute))
	p := newTestSAML2Provider(t, cert)

	w := serveSAMLCallback(t, p, raw, "") // no cookie attached

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestSAML2CallbackHandler_ForgedSignature_Rejected(t *testing.T) {
	gin.SetMode(gin.TestMode)
	now := time.Now().UTC()
	raw, cert := buildSignedSAMLResponse(t, "user@example.com", "req-http-3", now.Add(-time.Minute), now.Add(5*time.Minute))
	tampered := []byte(strings.Replace(string(raw), "user@example.com", "admin@example.com", 1))
	p := newTestSAML2Provider(t, cert)

	w := serveSAMLCallback(t, p, tampered, "req-http-3")

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for tampered assertion, got %d body=%s", w.Code, w.Body.String())
	}
}

// serveSAMLCallback routes a simulated IdP POST of SAMLResponse to
// /auth/callback through a real gin.Engine (rather than invoking the
// gin.HandlerFunc directly), so response status flushing behaves exactly as
// it does in production — gin only guarantees a buffered WriteHeader is
// flushed to the underlying ResponseWriter at the end of Engine routing,
// which calling a handler function in isolation bypasses. cookieRequestID
// empty omits the saml_request_id cookie entirely.
func serveSAMLCallback(t *testing.T, p *SAML2Provider, rawResponse []byte, cookieRequestID string) *httptest.ResponseRecorder {
	t.Helper()

	router := gin.New()
	router.POST("/auth/callback", p.CallbackHandler())

	form := url.Values{}
	form.Set("SAMLResponse", base64.StdEncoding.EncodeToString(rawResponse))

	req := httptest.NewRequest(http.MethodPost, "/auth/callback", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	if cookieRequestID != "" {
		req.AddCookie(&http.Cookie{Name: "saml_request_id", Value: cookieRequestID})
	}

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	return w
}
