# Compliance Posture

This document outlines SASEWaddle's compliance design and current limitations. Formal certifications (SOC 2 Type II, ISO 27001) are planned but not yet completed.

## Framework Alignment

| Framework | Status | Notes |
|-----------|--------|-------|
| **NIST Cybersecurity Framework** | Aligned | Core functions (Identify, Protect, Detect) implemented |
| **GDPR** | Partial | Data protection controls in place; see Known Gaps below |
| **HIPAA** | N/A | No PHI processing — regulatory requirement does not apply |
| **PCI DSS** | N/A | No payment card data processing — regulatory requirement does not apply |
| **SOC 2 Type II** | Roadmap | Planned for future certification |
| **ISO 27001** | Roadmap | Designed toward alignment; certification not yet completed |

## What SASEWaddle Does

✅ **Implemented Security Controls**
- TLS 1.3 for all API communications
- Tenant isolation at the application layer
- Per-service database accounts (no shared credentials)
- Dependency vulnerability scanning
- Semgrep SAST security gate in CI/CD
- OpenTelemetry observability (logs + traces + metrics)
- X.509 certificate lifecycle management
- JWT token validation with expiration checks
- Multi-factor authentication support

## Known Gaps (Roadmap)

❌ **Not Yet Implemented**
- Data subject access requests (DSAR) / erasure paths
- Comprehensive audit logging system (currently application-level only)
- User consent mechanisms (for GDPR)
- Records of Processing Activity (RoPA) / Data Processing Agreements (DPA)
- Formal audit log retention and tamper-proofing

These gaps represent planned work, not design flaws. They are tracked as compliance roadmap items and do not prevent deployment in regulated environments, though customers should assess risk tolerance for their specific regulatory context.

## Deployment Considerations

For regulated deployments, consider:
1. Document SASEWaddle's control set against your regulatory requirements
2. Implement additional organizational controls (e.g., access logs at the K8s/infrastructure layer)
3. Work with the SASEWaddle team on a Data Processing Agreement (DPA) if GDPR applies
4. Plan for future audit log migration when that feature is available
