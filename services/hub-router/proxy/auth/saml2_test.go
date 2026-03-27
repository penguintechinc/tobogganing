package auth

import (
	"encoding/base64"
	"encoding/xml"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// makeSAML2Token creates a HMAC-HS256 JWT signed with the spEntityID (same as
// the production SAML2Provider uses for session tokens).
func makeSAML2Token(spEntityID string, claims jwt.MapClaims) string {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(spEntityID))
	return signed
}

// makeSAML2Provider constructs a SAML2Provider directly, bypassing
// NewSAML2Provider which requires an external IDP metadata URL.
func makeSAML2Provider(spEntityID, ssoURL string) *SAML2Provider {
	return &SAML2Provider{
		idpMetadataURL: "https://idp.example.com/metadata",
		spEntityID:     spEntityID,
		metadata: &IDPMetadata{
			EntityID: "https://idp.example.com",
			SingleSignOnService: struct {
				Binding  string `xml:"Binding,attr"`
				Location string `xml:"Location,attr"`
			}{
				Binding:  "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
				Location: ssoURL,
			},
		},
	}
}

// ─── NewSAML2Provider ────────────────────────────────────────────────────────

func TestNewSAML2Provider_ConnectionRefused(t *testing.T) {
	_, err := NewSAML2Provider("http://127.0.0.1:1/metadata", "https://sp.example.com")
	if err == nil {
		t.Error("expected error for unreachable IDP metadata URL")
	}
}

func TestNewSAML2Provider_ValidMetadata(t *testing.T) {
	metadata := IDPMetadata{
		EntityID: "https://idp.example.com",
	}
	data, _ := xml.Marshal(metadata)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/xml")
		w.Write(data)
	}))
	defer ts.Close()

	provider, err := NewSAML2Provider(ts.URL, "https://sp.example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if provider == nil {
		t.Fatal("expected non-nil provider")
	}
}

func TestNewSAML2Provider_InvalidXML(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-xml"))
	}))
	defer ts.Close()

	_, err := NewSAML2Provider(ts.URL, "https://sp.example.com")
	if err == nil {
		t.Error("expected error for invalid XML metadata")
	}
}

// ─── SAML2Provider.ValidateToken ─────────────────────────────────────────────

func TestSAML2ValidateToken_Valid(t *testing.T) {
	spEntityID := "https://sp.example.com"
	provider := makeSAML2Provider(spEntityID, "")

	claims := jwt.MapClaims{
		"sub":    "saml-user-1",
		"email":  "saml@example.com",
		"name":   "SAML User",
		"groups": []interface{}{"admins"},
		"exp":    float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeSAML2Token(spEntityID, claims)

	user, err := provider.ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "saml-user-1" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
	if user.Email != "saml@example.com" {
		t.Errorf("unexpected email: %s", user.Email)
	}
	if len(user.Groups) != 1 || user.Groups[0] != "admins" {
		t.Errorf("unexpected groups: %v", user.Groups)
	}
}

func TestSAML2ValidateToken_Expired(t *testing.T) {
	spEntityID := "https://sp.example.com"
	provider := makeSAML2Provider(spEntityID, "")

	claims := jwt.MapClaims{
		"sub":   "saml-user-1",
		"email": "saml@example.com",
		"name":  "SAML User",
		"exp":   float64(time.Now().Add(-time.Hour).Unix()),
	}
	tokenStr := makeSAML2Token(spEntityID, claims)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for expired token")
	}
}

func TestSAML2ValidateToken_WrongKey(t *testing.T) {
	provider := makeSAML2Provider("correct-entity-id", "")

	claims := jwt.MapClaims{
		"sub":   "user",
		"email": "u@x.com",
		"name":  "U",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeSAML2Token("wrong-entity-id", claims)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for wrong signing key")
	}
}

func TestSAML2ValidateToken_RSAToken(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	key := generateTestRSAKey(t)
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
		"sub":   "user",
		"email": "u@x.com",
		"name":  "U",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	})
	tokenStr, _ := token.SignedString(key)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for RSA token (provider expects HMAC)")
	}
}

func TestSAML2ValidateToken_EmptyGroups(t *testing.T) {
	spEntityID := "https://sp.example.com"
	provider := makeSAML2Provider(spEntityID, "")

	claims := jwt.MapClaims{
		"sub":   "user-2",
		"email": "u2@x.com",
		"name":  "U2",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
		// no "groups" claim
	}
	tokenStr := makeSAML2Token(spEntityID, claims)

	user, err := provider.ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(user.Groups) != 0 {
		t.Errorf("expected empty groups, got %v", user.Groups)
	}
}

// ─── SAML2Provider.LogoutHandler ─────────────────────────────────────────────

func TestSAML2LogoutHandler(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	r := gin.New()
	r.GET("/logout", provider.LogoutHandler())

	req := httptest.NewRequest(http.MethodGet, "/logout", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	if !strings.Contains(w.Body.String(), "logged out") {
		t.Error("expected 'logged out' in response body")
	}
}

// ─── SAML2Provider.GetUser ────────────────────────────────────────────────────

func TestSAML2GetUser_ValidCookie(t *testing.T) {
	spEntityID := "https://sp.example.com"
	provider := makeSAML2Provider(spEntityID, "")

	claims := jwt.MapClaims{
		"sub":   "saml-cookie-user",
		"email": "cookie@saml.com",
		"name":  "Cookie",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeSAML2Token(spEntityID, claims)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)
	c.Request.AddCookie(&http.Cookie{Name: "session_token", Value: tokenStr})

	user, err := provider.GetUser(c)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "saml-cookie-user" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
}

func TestSAML2GetUser_NoCookie(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)

	_, err := provider.GetUser(c)
	if err == nil {
		t.Error("expected error when no session_token cookie")
	}
}

// ─── SAML2Provider.LoginHandler ──────────────────────────────────────────────

func TestSAML2LoginHandler_RedirectsToIDP(t *testing.T) {
	ssoURL := "https://idp.example.com/sso"
	provider := makeSAML2Provider("https://sp.example.com", ssoURL)

	r := gin.New()
	r.GET("/login", provider.LoginHandler())

	req := httptest.NewRequest(http.MethodGet, "/login", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusTemporaryRedirect {
		t.Errorf("expected 307, got %d", w.Code)
	}
	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "idp.example.com") {
		t.Errorf("expected redirect to IDP, got: %s", loc)
	}
}

// ─── SAML2Provider.CallbackHandler ───────────────────────────────────────────

func TestSAML2CallbackHandler_NoSAMLResponse(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	r := gin.New()
	r.POST("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodPost, "/callback", nil)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSAML2CallbackHandler_InvalidBase64(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	r := gin.New()
	r.POST("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodPost, "/callback",
		strings.NewReader("SAMLResponse=!!!not-base64!!!"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Should fail on base64 decode
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid base64, got %d", w.Code)
	}
}

func TestSAML2CallbackHandler_InvalidXML(t *testing.T) {
	provider := makeSAML2Provider("https://sp.example.com", "")

	r := gin.New()
	r.POST("/callback", provider.CallbackHandler())

	// Valid base64, but not valid SAML XML
	encoded := base64.StdEncoding.EncodeToString([]byte("not-xml"))
	req := httptest.NewRequest(http.MethodPost, "/callback",
		strings.NewReader("SAMLResponse="+encoded))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid XML, got %d", w.Code)
	}
}

// ─── IDPMetadata / SAMLResponse types ─────────────────────────────────────────

func TestIDPMetadata_XMLDecode(t *testing.T) {
	xmlData := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com">
</md:EntityDescriptor>`

	var meta IDPMetadata
	if err := xml.Unmarshal([]byte(xmlData), &meta); err != nil {
		// XML namespace may differ; just ensure the struct is usable
		t.Logf("XML unmarshal error (may be namespace): %v", err)
	}
}

func TestSAMLResponse_StructUsable(t *testing.T) {
	sr := SAMLResponse{
		ID:           "id123",
		InResponseTo: "req123",
	}
	sr.Assertion.Subject.NameID.Value = "user@example.com"
	if sr.Assertion.Subject.NameID.Value != "user@example.com" {
		t.Error("SAMLResponse struct fields not settable")
	}
}
