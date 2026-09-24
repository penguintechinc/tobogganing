# Security Policy

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately to **security@penguintech.io**. If you would like to encrypt your
report, ask in your first message and we will arrange a key exchange.

Please include whatever you have:

- A description of the vulnerability and the component it affects
- Steps to reproduce, or a proof of concept
- Your assessment of the impact
- Any suggested mitigation
- How you would like to be credited, if at all

### What happens next

| Stage | Target |
|---|---|
| Acknowledgement of your report | Within 48 hours |
| Initial assessment and severity triage | Within 5 business days |
| Fix developed and tested | Severity-dependent; critical issues take priority over roadmap work |
| Coordinated disclosure | Timed with you — we will not publish before you are ready |
| Public advisory and credit | On release of the fix, crediting you unless you prefer otherwise |

We will keep you updated as the report moves through these stages. If you do not
hear back within 48 hours, please follow up — a missed report is a bug in our
process and we want to know about it.

## Supported Versions

| Version | Supported |
|---|---|
| 1.2.x | :white_check_mark: |
| < 1.2 | :x: |

Security fixes land on the current release line. The previous minor version
receives fixes for high and critical severity issues; older lines do not.

## Safe Harbour

We will not pursue legal action against researchers who act in good faith:
access only data that is clearly your own or test data, avoid privacy violations
and service degradation, do not exfiltrate data beyond what is needed to
demonstrate the issue, and give us reasonable time to fix things before going
public. Report promptly and we will treat you as a collaborator, not a threat.

## How Tobogganing Is Built

Security controls that are configuration are security controls someone forgets
to turn on. These are defaults in this codebase:

- **Multi-tenant isolation** — the tenant boundary is enforced at the query layer
  and evaluated before any other authorization check
- **OIDC scope-based authorization** — permissions resolve to scopes, never role
  names; roles are pre-bundled scope sets
- **Short-lived JWTs** — one-hour default expiry, refresh tokens rotate on every
  use, and a reused refresh token revokes the whole chain
- **Service identity** — SPIFFE-ready, accepting mTLS/X.509-SVID; every
  inter-service call carries a short-lived signed JWT regardless of transport
- **Encryption in transit and at rest** — TLS 1.2+ minimum, at-rest encryption on
  every store holding sensitive data, backups included
- **PII tokenization** — a single identity table; everything else references UUIDs
- **Input and output validation** — inputs validated server-side, responses scoped
  to an explicit schema so an endpoint cannot silently over-share
- **Rootless containers** — rootless runtime and non-root process, both layers
- **Default-deny networking** — deny-by-default network policy, filtered egress,
  external access scoped to the port the service actually serves
- **Pinned dependencies** — every dependency pinned to an immutable, verified
  reference; no floating tags
- **Automated scanning** — SAST, DAST, dependency audit, container, IaC, and
  secrets scanning run in pre-commit and pre-push hooks as well as CI
- **Enforced coverage** — 90% minimum across lines, branches, functions, and
  statements; builds fail below it, and reported bugs get a regression test

## Compliance

Tobogganing is **designed to support** organizations working toward SOC 2, ISO
27001, NIST CSF, HIPAA, PCI DSS, and GDPR obligations — through audit logging,
access control, encryption, and data handling built to those expectations.

This is a statement about architecture, not a certification claim. We do not
assert that this project is certified under any of these frameworks. Where a
formal attestation is required, contact us and we will tell you honestly what
does and does not exist today.

## Security Updates

Advisories are published as GitHub Security Advisories on this repository and
noted in release notes. Watch this repository's releases to be notified.
