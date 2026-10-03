//! Wire types for the firewall rules the Manager/hub-api control plane
//! serves — the Rust port of the Go source's `FirewallRule`, `UserRules`,
//! and `AllRulesResponse` structs
//! (`services/hub-router/proxy/firewall/manager.go`). Field names and
//! JSON shape are preserved exactly (`#[serde(rename_all = ...)]` is not
//! needed — these are already `snake_case` on the wire, matching the Go
//! struct tags) so this crate can deserialize the live
//! `GET /api/v1/firewall/rules` response unchanged.

use std::collections::HashMap;

/// One firewall rule: a `pattern` (interpreted per the category it's
/// filed under — domain, IP, CIDR range, regex, or protocol-5-tuple
/// selector) plus a `priority` (lower number = evaluated first — see
/// [`crate::engine::RuleSet`]). The five `src_ip`/`dst_ip`/`protocol`/
/// `src_port`/`dst_port`/`direction` fields only apply to protocol rules
/// (`RuleKind::ProtocolRule`); they're unused (left empty) for every
/// other rule kind, mirroring the Go struct's `omitempty` tags.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct FirewallRule {
    pub pattern: String,
    pub priority: i64,
    #[serde(default)]
    pub description: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub src_ip: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub dst_ip: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub protocol: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub src_port: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub dst_port: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub direction: String,
}

/// The ten rule categories a user's firewall configuration is organized
/// into on the wire — the Rust port of the Go source's anonymous nested
/// `Rules struct { ... }` field inside `UserRules`. [`crate::engine::RuleSet::build`]
/// flattens these into one priority-ordered list.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct RuleCategories {
    #[serde(default)]
    pub allow_domains: Vec<FirewallRule>,
    #[serde(default)]
    pub deny_domains: Vec<FirewallRule>,
    #[serde(default)]
    pub allow_ips: Vec<FirewallRule>,
    #[serde(default)]
    pub deny_ips: Vec<FirewallRule>,
    #[serde(default)]
    pub allow_ip_ranges: Vec<FirewallRule>,
    #[serde(default)]
    pub deny_ip_ranges: Vec<FirewallRule>,
    #[serde(default)]
    pub allow_url_patterns: Vec<FirewallRule>,
    #[serde(default)]
    pub deny_url_patterns: Vec<FirewallRule>,
    #[serde(default)]
    pub allow_protocol_rules: Vec<FirewallRule>,
    #[serde(default)]
    pub deny_protocol_rules: Vec<FirewallRule>,
}

/// One user's full firewall configuration, as served by the Manager
/// control plane — the Rust port of the Go source's `UserRules`.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct UserRules {
    pub user_id: String,
    pub timestamp: String,
    pub rules: RuleCategories,
}

/// `GET /api/v1/firewall/rules`'s full response body — the Rust port of
/// the Go source's `AllRulesResponse`.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct AllRulesResponse {
    pub timestamp: String,
    pub rules_count: i64,
    #[serde(default)]
    pub user_rules: HashMap<String, UserRules>,
}
