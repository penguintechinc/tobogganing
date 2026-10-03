//! Hub router firewall subsystem — the Rust port of the Go headend's
//! priority-based, allow/deny firewall engine
//! (`services/hub-router/proxy/firewall/manager.go`). See each
//! submodule's doc for its slice of the port: [`matcher`] (pure
//! per-rule-type match predicates, characterization-tested against the
//! Go source's observed behavior before this port's own logic existed),
//! [`engine`] (priority ordering + evaluation, including the
//! per-request-sort performance fix — see its doc), [`manager`]
//! (periodic control-plane fetch + the public API), [`rule`] (wire
//! types), and [`metrics`] (OTel instrumentation).

pub mod engine;
pub mod manager;
mod matcher;
mod metrics;
pub mod rule;

pub use engine::{Access, CheckOutcome, RuleKind, RuleSet};
pub use manager::{Manager, ManagerError, TokenProvider};
pub use rule::{AllRulesResponse, FirewallRule, RuleCategories, UserRules};
