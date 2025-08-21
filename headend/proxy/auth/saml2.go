package auth

import (
    "encoding/base64"
    "encoding/xml"
    "fmt"
    "net/http"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/golang-jwt/jwt/v5"
)

type SAML2Provider struct {
    idpMetadataURL string
    spEntityID     string
    metadata       *IDPMetadata
}

type IDPMetadata struct {
    EntityID            string `xml:"entityID,attr"`
    SingleSignOnService struct {
        Binding  string `xml:"Binding,attr"`
        Location string `xml:"Location,attr"`
    } `xml:"IDPSSODescriptor>SingleSignOnService"`
    Certificate string `xml:"IDPSSODescriptor>KeyDescriptor>KeyInfo>X509Data>X509Certificate"`
}

type SAMLResponse struct {
    XMLName      xml.Name `xml:"urn:oasis:names:tc:SAML:2.0:protocol Response"`
    ID           string   `xml:"ID,attr"`
    InResponseTo string   `xml:"InResponseTo,attr"`
    Assertion    struct {
        Subject struct {
            NameID struct {
                Value  string `xml:",chardata"`
                Format string `xml:"Format,attr"`
            } `xml:"NameID"`
        } `xml:"Subject"`
        AttributeStatement struct {
            Attributes []struct {
                Name       string   `xml:"Name,attr"`
                NameFormat string   `xml:"NameFormat,attr"`
                Values     []string `xml:"AttributeValue"`
            } `xml:"Attribute"`
        } `xml:"AttributeStatement"`
    } `xml:"Assertion"`
}

func NewSAML2Provider(idpMetadataURL, spEntityID string) (*SAML2Provider, error) {
    provider := &SAML2Provider{
        idpMetadataURL: idpMetadataURL,
        spEntityID:     spEntityID,
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
    defer resp.Body.Close()
    
    var metadata IDPMetadata
    if err := xml.NewDecoder(resp.Body).Decode(&metadata); err != nil {
        return fmt.Errorf("failed to parse IDP metadata: %w", err)
    }
    
    p.metadata = &metadata
    return nil
}

func (p *SAML2Provider) LoginHandler() gin.HandlerFunc {
    return func(c *gin.Context) {
        // Generate SAML Auth Request
        authRequest := p.generateAuthRequest()
        
        // Encode and redirect to IDP
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
        
        decoded, err := base64.StdEncoding.DecodeString(samlResponse)
        if err != nil {
            c.JSON(http.StatusBadRequest, gin.H{"error": "invalid SAML response"})
            return
        }
        
        var response SAMLResponse
        if err := xml.Unmarshal(decoded, &response); err != nil {
            c.JSON(http.StatusBadRequest, gin.H{"error": "failed to parse SAML response"})
            return
        }
        
        // TODO: Validate SAML response signature
        
        // Extract user information
        user := &User{
            ID:    response.Assertion.Subject.NameID.Value,
            Email: response.Assertion.Subject.NameID.Value,
        }
        
        // Extract attributes
        for _, attr := range response.Assertion.AttributeStatement.Attributes {
            switch attr.Name {
            case "email", "mail":
                if len(attr.Values) > 0 {
                    user.Email = attr.Values[0]
                }
            case "name", "displayName":
                if len(attr.Values) > 0 {
                    user.Name = attr.Values[0]
                }
            case "groups", "memberOf":
                user.Groups = attr.Values
            }
        }
        
        // Create session token
        sessionToken := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
            "sub":    user.ID,
            "email":  user.Email,
            "name":   user.Name,
            "groups": user.Groups,
            "exp":    time.Now().Add(24 * time.Hour).Unix(),
        })
        
        tokenString, err := sessionToken.SignedString([]byte(p.spEntityID))
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
        return []byte(p.spEntityID), nil
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

func (p *SAML2Provider) generateAuthRequest() string {
    requestID := fmt.Sprintf("id-%d", time.Now().UnixNano())
    issueInstant := time.Now().UTC().Format(time.RFC3339)
    
    return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest 
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="%s"
    Version="2.0"
    IssueInstant="%s"
    Destination="%s"
    AssertionConsumerServiceURL="https://localhost:8443/auth/callback"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>%s</saml:Issuer>
</samlp:AuthnRequest>`, requestID, issueInstant, p.metadata.SingleSignOnService.Location, p.spEntityID)
}