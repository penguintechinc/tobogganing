# SASE Block Page Serving Contract

**Status**: Design specification for data-plane implementation (inspection points and inline gateways)  
**Version**: 1.0  
**Date**: 2026-08-06  

## Overview

This document specifies how the data plane (Inspection Points, inline gateways, and edge enforcement agents) should render and serve block pages when an enforcement action of `block` or `soft_block` is triggered by the SASE security system. It forms the contract between the control plane (hub-api) and the data plane for block page customization and routing.

## Trigger Conditions

Block page serving is triggered when the inspection point evaluates an `EnforcementAction` of:
- `block` — immediate block, serve block page (HTTP 403) or redirect with `X-Block-*` headers
- `soft_block` — interstitial block, serve soft-block page with continuation option (HTTP 200 with acknowledgement form)

The data plane MUST NOT serve block pages on other actions (`allow`, `log_only`, `drop`).

## Configuration Pull

1. The inspection point pulls block page and routing configuration via the hub-api control plane at a regular cadence (daily "freshclam" style refresh, not per-request gRPC).
2. Configuration is cached locally in the inspection point for low-latency enforcement.
3. On each pull, the inspection point retrieves:
   - Live `BlockPage` markdown documents (identified by name)
   - `BlockRoute` mappings from source_type → destination (page or external URL)

## Routing Resolution

When a `block` or `soft_block` action fires on a request, the inspection point:

1. Extracts the block's `source_type` (e.g., `web-category:gambling`, `oob-analysis:malware`, `custom-rule:<id>`, `soft-block`)
2. Looks up the corresponding `BlockRoute` in the cached routing table via `resolve(tenant, source_type)`
3. The route may specify either:
   - **Page destination**: serve a locally-cached `BlockPage` markdown, rendered to HTML
   - **External destination**: redirect to a customer-operated server with block context headers
   - **Missing route**: fall back to a global default page (never an error page that leaks internals)

## Block Page Serving (`destination_kind == "page"`)

### For `block` (Hard Block)

1. Fetch the live `BlockPage` markdown from local cache (identified by `page_id`).
2. Substitute template variables in the markdown (see **Template Variables**).
3. Render markdown to HTML using a markdown library (e.g., Python `markdown`, Rust `pulldown-cmark`, Go `goldmark`).
4. **Sanitize** the resulting HTML to strip any dangerous tags/attributes, even though the markdown source is admin-authored (defense in depth):
   - Remove `<script>`, `<style>` tags and their content.
   - Remove event handler attributes (`onclick`, `onload`, etc.).
   - Keep safe tags: headings, paragraphs, links, images, lists, blockquotes, code blocks.
5. Serve the sanitized HTML as the response body with HTTP status **403 Forbidden**.

### For `soft_block` (Soft Block / Interstitial)

1-4. Same as hard block (fetch, substitute, render, sanitize).
5. Serve the sanitized HTML as an interstitial page with HTTP status **200 OK**.
6. Include a continuation control (form or button) that allows the user to acknowledge and proceed:
   - A POST endpoint that validates the acknowledgement (user agrees to the block reason, logs the interaction).
   - Redirect to the originally blocked URL after acknowledgement (implementation specific — may require additional policy evaluation).

Template variables for soft-block include an additional `{{continue_url}}` variable pointing to the acknowledgement endpoint.

## External Redirect (`destination_kind == "external"`)

1. The `BlockRoute.external_url` specifies a customer-operated URL (e.g., `https://customer.example.com/block-page`).
2. The inspection point issues a **redirect** (HTTP 302 or 307) to that URL.
3. The redirect response includes a set of context headers (the `X-Block-*` header contract):
   - `X-Blocked-URL` — the original URL that was blocked (URL-encoded)
   - `X-Block-Category` — the content category (from the enforcement context)
   - `X-Block-Rule-ID` — the rule or policy ID that triggered the block
   - `X-Block-Source` — the source type (e.g., `web-category:gambling`)
   - `X-Block-User` — the user's UUID (not email/PII)
   - `X-Block-Tenant` — the tenant ID (for customer's multi-tenant tracking)
   - `X-Block-Reason` — human-readable reason (must not include PII or internal details)
   - `X-Timestamp` — ISO8601 timestamp of the block decision (for audit trails)

The customer's server receives these headers and renders its own custom block page. This allows enterprises to apply their own branding and workflows while the inspection point enforces policy.

## Template Variables

The following variables can be substituted in markdown block pages via `{{variable_name}}` syntax:

| Variable | Example Value | Purpose |
|---|---|---|
| `{{blocked_url}}` | `https://example-gambling.com/` | The URL that triggered the block |
| `{{category}}` | `Gambling` | Web category or threat classification |
| `{{reason}}` | `Promotes online gambling` | Human-readable reason for the block |
| `{{user}}` | `alice@company.com` (preferred) or `alice` | User identifier (may be masked; avoid full PII) |
| `{{org}}` | `ACME Corp` | Organization/tenant name |
| `{{support_link}}` | `https://support.company.com/blocked` | Link to support documentation |
| `{{appeal_link}}` | `https://appeal.company.com?url=...` | Link to submit a block appeal |
| `{{timestamp}}` | `2026-08-06T12:00:00Z` | ISO8601 timestamp of the block |
| `{{continue_url}}` | `https://gw.internal/continue?token=abc123` | (Soft-block only) URL to continue after acknowledgement |

**Undefined variables**: If a template variable is not provided by the data plane, leave it as-is (e.g., `{{undefined_var}}` remains in the HTML). This allows graceful degradation if the data plane doesn't provide a value for a given variable.

## Global Default Page

If no `BlockRoute` is found for a given `source_type`, the inspection point MUST fall back to a **global default page**. This is a fail-safe to prevent error pages from leaking implementation details.

The global default is typically a generic `BlockRoute` with `source_type == "default"`, which must exist in every tenant's routing configuration. If no default exists, the inspection point must have a hardcoded fallback page (e.g., "Access Denied") rendered with minimal variables.

Example default route configuration:
```json
{
  "source_type": "default",
  "destination_kind": "page",
  "page_id": "default-block-page-id"
}
```

## Configuration Schema (Reference)

The inspection point cache structures the configuration as:

```python
# BlockPage (cached from hub-api, identified by page_id)
class BlockPage:
    id: str
    name: str
    markdown: str  # The markdown source to render
    status: str    # "live" only (drafts are not served)
    version: int   # For audit trails

# BlockRoute (cached from hub-api, per tenant)
class BlockRoute:
    source_type: str        # e.g., "web-category:gambling", "oob-analysis:malware", "default"
    destination_kind: str   # "page" or "external"
    page_id: str | None     # If destination_kind == "page"
    external_url: str | None # If destination_kind == "external"
    # Governance metadata (informational only at data plane):
    created_by: str
    ticket: str
    notes: str
    scope: str
```

The inspection point maintains a local index:
- `routes_by_source_type[tenant][source_type] -> BlockRoute`
- `pages_by_id[page_id] -> BlockPage`

## Rendering Algorithm (Pseudocode)

```
function serve_block(tenant, request, enforcement_action, source_type):
    # Resolve route
    route = resolve(tenant, source_type) or GLOBAL_DEFAULT
    if not route:
        # No route and no default — serve hardcoded emergency page
        return response(403, "Access Denied")
    
    if route.destination_kind == "page":
        # Fetch page
        page = pages_by_id.get(route.page_id)
        if not page:
            return response(403, EMERGENCY_PAGE)  # Page not found (should not happen)
        
        # Substitute variables
        variables = extract_variables(request, enforcement_action, source_type)
        html = render_markdown(page.markdown, variables)
        
        # Sanitize
        html = sanitize_html(html)
        
        # Serve
        if enforcement_action == "block":
            return response(403, html)
        elif enforcement_action == "soft_block":
            return response(200, html_with_continuation_form(html))
    
    elif route.destination_kind == "external":
        # External redirect
        headers = build_block_headers(tenant, request, enforcement_action, source_type)
        return redirect(route.external_url, status=302, headers=headers)
```

## Implementation Checklist

- [ ] Pull configuration from hub-api on startup and at regular intervals (daily minimum)
- [ ] Cache block pages and routes locally in the inspection point
- [ ] Implement `resolve(tenant, source_type)` with fallback to global default
- [ ] For page serving: substitute variables, render markdown, sanitize HTML
- [ ] For external redirect: construct `X-Block-*` headers, issue redirect
- [ ] Handle missing pages/routes gracefully (emergency fallback page)
- [ ] Log all block page serving decisions (source_type, route choice, page served)
- [ ] Test with malicious markdown (script tags, event handlers) to verify sanitization
- [ ] Expose resolved block page configuration in diagnostics (for troubleshooting)

## Security Considerations

1. **Markdown Sanitization**: Even though the markdown source is admin-authored (trusted input), sanitize the HTML output as a defense-in-depth measure. A compromised admin or injected markdown could otherwise execute scripts or inject styles.
2. **Variable Substitution**: Template variables are derived from the request and enforcement context (never from user input). No template variable contains executable code.
3. **HTML Entities**: Ensure all variable values are HTML-encoded when substituted into markdown (handled by the markdown library's escape behavior, but double-check).
4. **External Redirect Headers**: The `X-Block-*` headers must not expose sensitive internal details (policy IDs, internal IP addresses, etc.). Only include information the customer needs for their own block page.

## Examples

### Hard Block with Custom Page

```
Request: https://example-gambling.com/
Enforcement: block on web-category:gambling
Route: source_type="web-category:gambling" → page_id="gambling-block-page"
BlockPage(gambling-block-page):
  markdown: |
    # Access Blocked
    
    Your organization blocks access to **{{category}}** sites.
    - URL: {{blocked_url}}
    - Reason: {{reason}}
    
    [Contact support]({{support_link}}) or [appeal]({{appeal_link}})
    
    Blocked: {{timestamp}}

Variables:
  blocked_url: "example-gambling.com"
  category: "Gambling"
  reason: "Gambling sites violate company policy"
  user: "alice@company.com"
  support_link: "https://company.com/support"
  appeal_link: "https://appeal.company.com?url=example-gambling.com"
  timestamp: "2026-08-06T12:00:00Z"

Rendered HTML (sanitized):
  <h1>Access Blocked</h1>
  <p>Your organization blocks access to <strong>Gambling</strong> sites.</p>
  <ul>
    <li>URL: example-gambling.com</li>
    <li>Reason: Gambling sites violate company policy</li>
  </ul>
  <p><a href="https://company.com/support">Contact support</a> or <a href="https://appeal.company.com?url=example-gambling.com">appeal</a></p>
  <p>Blocked: 2026-08-06T12:00:00Z</p>

Response: HTTP 403 Forbidden + HTML body
```

### External Redirect

```
Request: https://example-malware.com/
Enforcement: block on oob-analysis:malware
Route: source_type="oob-analysis:malware" → external_url="https://customer.example.com/block"

Response: HTTP 302 Found
  Location: https://customer.example.com/block
  X-Blocked-URL: example-malware.com
  X-Block-Category: Malware
  X-Block-Source: oob-analysis:malware
  X-Block-User: user-uuid-1234
  X-Block-Tenant: tenant-abc
  X-Block-Reason: Detected malicious payload
  X-Timestamp: 2026-08-06T12:00:00Z

Customer's server receives headers and renders its own block page (branding, custom workflow, etc.)
```

## References

- Control plane API: `/api/v1/sase/blockpages/` (hub-api endpoints)
- SASE enforcement: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` → EnforcementAction
- Inspection point integration: (implementation-specific per gateway type)
