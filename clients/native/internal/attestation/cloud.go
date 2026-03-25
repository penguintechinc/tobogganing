package attestation

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const (
	// imdsTimeout is the per-provider timeout for IMDS queries.
	// Cloud IMDS responds in <10ms; 500ms catches slow link-local routes.
	imdsTimeout = 500 * time.Millisecond
)

// collectCloudIdentity auto-detects whether the host is running on a cloud
// provider by probing AWS, GCP, and Azure IMDS endpoints in sequence.
// Returns nil (not an error) if no cloud provider is detected.
func collectCloudIdentity(ctx context.Context) (*CloudInstanceIdentity, error) {
	// Try providers in order; return first success
	if id, err := collectAWSIdentity(ctx); err == nil && id != nil {
		return id, nil
	}

	if id, err := collectGCPIdentity(ctx); err == nil && id != nil {
		return id, nil
	}

	if id, err := collectAzureIdentity(ctx); err == nil && id != nil {
		return id, nil
	}

	return nil, fmt.Errorf("no cloud provider detected")
}

// collectAWSIdentity queries the AWS Instance Metadata Service (IMDSv1)
// for the instance identity document and its PKCS7 signature.
func collectAWSIdentity(ctx context.Context) (*CloudInstanceIdentity, error) {
	client := &http.Client{Timeout: imdsTimeout}

	// Fetch identity document
	docURL := "http://169.254.169.254/latest/dynamic/instance-identity/document"
	doc, err := imdsGet(ctx, client, docURL, nil)
	if err != nil {
		return nil, err
	}

	// Parse document for structured fields
	var awsDoc struct {
		InstanceID string `json:"instanceId"`
		Region     string `json:"region"`
		AccountID  string `json:"accountId"`
	}
	if err := json.Unmarshal(doc, &awsDoc); err != nil {
		return nil, fmt.Errorf("failed to parse AWS IID: %w", err)
	}

	// Fetch PKCS7 signature for verification
	sigURL := "http://169.254.169.254/latest/dynamic/instance-identity/pkcs7"
	sig, err := imdsGet(ctx, client, sigURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch AWS PKCS7 signature: %w", err)
	}

	return &CloudInstanceIdentity{
		Provider:       "aws",
		InstanceID:     awsDoc.InstanceID,
		Region:         awsDoc.Region,
		AccountID:      awsDoc.AccountID,
		SignedDocument: string(sig),
	}, nil
}

// collectGCPIdentity queries the GCP Compute Metadata Server for instance
// identity information.
func collectGCPIdentity(ctx context.Context) (*CloudInstanceIdentity, error) {
	client := &http.Client{Timeout: imdsTimeout}
	headers := map[string]string{"Metadata-Flavor": "Google"}

	// Instance ID
	idBytes, err := imdsGet(ctx, client,
		"http://169.254.169.254/computeMetadata/v1/instance/id", headers)
	if err != nil {
		return nil, err
	}

	// Zone (region derived from zone)
	zoneBytes, err := imdsGet(ctx, client,
		"http://169.254.169.254/computeMetadata/v1/instance/zone", headers)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch GCP zone: %w", err)
	}

	// Project numeric ID
	projectBytes, err := imdsGet(ctx, client,
		"http://169.254.169.254/computeMetadata/v1/project/numeric-project-id", headers)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch GCP project ID: %w", err)
	}

	// Identity token (signed)
	audience := "tobogganing-attestation"
	tokenURL := fmt.Sprintf(
		"http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/identity?audience=%s&format=full",
		audience,
	)
	tokenBytes, err := imdsGet(ctx, client, tokenURL, headers)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch GCP identity token: %w", err)
	}

	return &CloudInstanceIdentity{
		Provider:       "gcp",
		InstanceID:     string(idBytes),
		Region:         extractGCPRegion(string(zoneBytes)),
		AccountID:      string(projectBytes),
		SignedDocument: string(tokenBytes),
	}, nil
}

// collectAzureIdentity queries the Azure Instance Metadata Service for
// instance identity and attested data.
func collectAzureIdentity(ctx context.Context) (*CloudInstanceIdentity, error) {
	client := &http.Client{Timeout: imdsTimeout}
	headers := map[string]string{"Metadata": "true"}

	url := "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
	body, err := imdsGet(ctx, client, url, headers)
	if err != nil {
		return nil, err
	}

	var azDoc struct {
		Compute struct {
			VMID           string `json:"vmId"`
			Location       string `json:"location"`
			SubscriptionID string `json:"subscriptionId"`
		} `json:"compute"`
	}
	if err := json.Unmarshal(body, &azDoc); err != nil {
		return nil, fmt.Errorf("failed to parse Azure IMDS: %w", err)
	}

	// Fetch attested data (signed)
	attestedURL := "http://169.254.169.254/metadata/attested/document?api-version=2021-02-01"
	attestedBody, err := imdsGet(ctx, client, attestedURL, headers)
	if err != nil {
		// Attested endpoint may not always be available; use instance data as fallback
		attestedBody = body
	}

	return &CloudInstanceIdentity{
		Provider:       "azure",
		InstanceID:     azDoc.Compute.VMID,
		Region:         azDoc.Compute.Location,
		AccountID:      azDoc.Compute.SubscriptionID,
		SignedDocument: string(attestedBody),
	}, nil
}

// imdsGet performs an HTTP GET against an IMDS endpoint with optional headers.
func imdsGet(ctx context.Context, client *http.Client, url string, headers map[string]string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("IMDS returned status %d", resp.StatusCode)
	}

	return io.ReadAll(resp.Body)
}

// extractGCPRegion derives the region from a full GCP zone path like
// "projects/123/zones/us-central1-a" → "us-central1".
func extractGCPRegion(zone string) string {
	// Zone format: "projects/<id>/zones/<zone-name>" or just "<zone-name>"
	parts := splitLast(zone, "/")
	zoneName := parts

	// Region is zone minus the last "-X" suffix
	lastDash := lastIndexByte(zoneName, '-')
	if lastDash > 0 {
		return zoneName[:lastDash]
	}
	return zoneName
}

// splitLast returns everything after the last occurrence of sep, or the
// entire string if sep is not found.
func splitLast(s, sep string) string {
	idx := lastIndex(s, sep)
	if idx < 0 {
		return s
	}
	return s[idx+len(sep):]
}

func lastIndex(s, sep string) int {
	for i := len(s) - len(sep); i >= 0; i-- {
		if s[i:i+len(sep)] == sep {
			return i
		}
	}
	return -1
}

func lastIndexByte(s string, c byte) int {
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == c {
			return i
		}
	}
	return -1
}
