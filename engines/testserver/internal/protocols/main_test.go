//go:build !integration

package protocols_test

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"testing"
	"time"
)

var (
	testCAKey     *ecdsa.PrivateKey
	testCACert    *x509.Certificate
	testCACertDER []byte
	testCAFile    string
)

func TestMain(m *testing.M) {
	// Generate CA key pair
	var err error
	testCAKey, err = ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		panic(err)
	}

	// Create CA certificate template
	caTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "Test CA"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		IsCA:                  true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		BasicConstraintsValid: true,
	}

	// Create CA certificate
	testCACertDER, err = x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &testCAKey.PublicKey, testCAKey)
	if err != nil {
		panic(err)
	}

	// Parse CA certificate
	testCACert, err = x509.ParseCertificate(testCACertDER)
	if err != nil {
		panic(err)
	}

	// Write CA cert to temp file
	f, err := os.CreateTemp("", "test-ca-*.pem")
	if err != nil {
		panic(err)
	}
	testCAFile = f.Name()

	err = pem.Encode(f, &pem.Block{Type: "CERTIFICATE", Bytes: testCACertDER})
	if err != nil {
		f.Close()
		panic(err)
	}
	f.Close()

	// Set SSL_CERT_FILE BEFORE running tests so x509.SystemCertPool loads our CA
	oldSSLCertFile := os.Getenv("SSL_CERT_FILE")
	os.Setenv("SSL_CERT_FILE", testCAFile)

	// Set up fake traceroute binary
	tracerouteDir, err := os.MkdirTemp("", "test-bin-*")
	if err != nil {
		panic(err)
	}

	tracerouteScript := tracerouteDir + "/traceroute"
	// Conditional fake traceroute:
	// - -T (TCP trace mode): fail so TestTCPTrace exercises its TCP fallback path
	// - -p (UDP trace mode, passes explicit port with -p flag): fail so TestUDPTrace
	//   exercises its UDP fallback path
	// - Default (ICMP modes): succeed with one hop so testTraceroute and TestTraceroute
	//   both parse output and cover their success paths
	scriptContent := `#!/bin/sh
for arg in "$@"; do
  case "$arg" in
    -T) echo "traceroute: TCP mode requires root" >&2; exit 1 ;;
    -p) echo "traceroute: UDP port mode not permitted" >&2; exit 1 ;;
  esac
done
echo "traceroute to 127.0.0.1 (127.0.0.1), 30 hops max, 60 byte packets"
echo " 1  127.0.0.1 (127.0.0.1)  0.123 ms  0.456 ms  0.789 ms"
`
	err = os.WriteFile(tracerouteScript, []byte(scriptContent), 0755)
	if err != nil {
		panic(err)
	}

	oldPATH := os.Getenv("PATH")
	os.Setenv("PATH", tracerouteDir+":"+oldPATH)

	// Run tests
	code := m.Run()

	// Cleanup
	os.Setenv("PATH", oldPATH)
	if oldSSLCertFile != "" {
		os.Setenv("SSL_CERT_FILE", oldSSLCertFile)
	} else {
		os.Unsetenv("SSL_CERT_FILE")
	}
	os.Remove(testCAFile)
	os.Remove(tracerouteScript)
	os.Remove(tracerouteDir)

	os.Exit(code)
}
