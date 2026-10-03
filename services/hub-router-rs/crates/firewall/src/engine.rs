//! Priority-ordered rule evaluation — the Rust port of `CheckAccess`'s
//! matching loop (`services/hub-router/proxy/firewall/manager.go`). Also
//! contains THE deliberate behavior change this PR makes (a performance
//! fix, not a Go-bug fix): [`RuleSet::build`] sorts the combined rule
//! list ONCE, when a [`RuleSet`] is constructed from a freshly
//! fetched/updated [`crate::rule::UserRules`] — never on every
//! [`RuleSet::check`] call. See [`RuleSet`]'s doc for the before/after
//! complexity.

use crate::matcher;
use crate::rule::{FirewallRule, UserRules};

/// Which of the five rule categories a [`FirewallRule`] belongs to —
/// determines which `matcher` predicate evaluates it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuleKind {
    Domain,
    Ip,
    IpRange,
    UrlPattern,
    ProtocolRule,
}

/// Whether a matched rule allows or denies the request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Access {
    Allow,
    Deny,
}

#[derive(Debug, Clone)]
struct PriorityRule {
    rule: FirewallRule,
    kind: RuleKind,
    access: Access,
}

/// The result of [`RuleSet::check`] — distinguishes *why* access was
/// denied (matched an explicit deny rule vs. no rule matched at all) for
/// logging/metrics, while [`CheckOutcome::allowed`] gives callers the
/// plain boolean the Go source's `CheckAccess bool` return represented.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CheckOutcome {
    Allowed { pattern: String, priority: i64 },
    DeniedByRule { pattern: String, priority: i64 },
    DeniedNoMatch,
}

impl CheckOutcome {
    /// The Go source's `CheckAccess` return value — `true` only when an
    /// explicit allow rule matched.
    pub fn allowed(&self) -> bool {
        matches!(self, CheckOutcome::Allowed { .. })
    }

    /// Metric/log label: `"allow"`, `"deny_matched"`, or
    /// `"deny_no_match"`.
    pub fn reason(&self) -> &'static str {
        match self {
            CheckOutcome::Allowed { .. } => "allow",
            CheckOutcome::DeniedByRule { .. } => "deny_matched",
            CheckOutcome::DeniedNoMatch => "deny_no_match",
        }
    }
}

/// A user's firewall rules, flattened and sorted by priority exactly
/// once (at construction) rather than on every access check.
///
/// ## The fix-while-porting: per-request sort removed
///
/// The Go source's `CheckAccess` rebuilt `allRules` (a fresh
/// `[]priorityRule` slice, reallocated from scratch every call) from all
/// ten rule categories and then **bubble-sorted** it — an `i`/`j`
/// nested-loop adjacent-swap sort, `O(n^2)`, not merely the `O(n log n)`
/// a reasonable sort would cost — on **every single** `CheckAccess`
/// call, i.e. every proxied request/packet a user's traffic generated.
/// The rule set does not change between requests, only between rule
/// fetches (every 30-90s), so this was pure wasted CPU repeated at the
/// connection-processing hot path, and actually worse than the
/// `O(n log n)` baseline this port was scoped to fix.
///
/// This port moves the sort to construction time: [`RuleSet::build`] is
/// called once per [`crate::manager::Manager::fetch_rules`] refresh (not
/// once per request), running a single stable `sort_by_key`
/// (`O(n log n)`, Rust's slice sort is a stable, Timsort-derived
/// algorithm — stable so that two rules sharing the same `priority`
/// resolve in the exact same tie-break order the Go bubble sort
/// produced, given the identical pre-sort insertion order below).
/// [`RuleSet::check`] is then a plain `O(n)` linear scan with early-exit
/// on the first match (best case `O(1)`).
///
/// | | Go (before) | This port (after) |
/// |---|---|---|
/// | Per `CheckAccess`/`check` call | `O(n^2)` (rebuild + bubble sort + scan), every call | `O(n)` scan, early-exit |
/// | Per rules refresh | — (no separate step) | `O(n log n)` sort, once |
#[derive(Debug, Clone)]
pub struct RuleSet {
    rules: Vec<PriorityRule>,
}

impl RuleSet {
    /// Builds a presorted [`RuleSet`] from one user's raw [`UserRules`].
    /// Insertion order before sorting deliberately matches the Go
    /// source's `allRules` construction order exactly — deny before
    /// allow, within domain/ip/ip_range/url_pattern/protocol_rule order
    /// — so that, combined with a stable sort, two rules sharing the
    /// same `priority` resolve in the identical tie-break order the Go
    /// bubble sort produced.
    pub fn build(user_rules: &UserRules) -> Self {
        let categories = &user_rules.rules;
        let total = categories.deny_domains.len()
            + categories.allow_domains.len()
            + categories.deny_ips.len()
            + categories.allow_ips.len()
            + categories.deny_ip_ranges.len()
            + categories.allow_ip_ranges.len()
            + categories.deny_url_patterns.len()
            + categories.allow_url_patterns.len()
            + categories.deny_protocol_rules.len()
            + categories.allow_protocol_rules.len();
        let mut rules = Vec::with_capacity(total);

        let mut push = |src: &[FirewallRule], kind: RuleKind, access: Access| {
            for rule in src {
                rules.push(PriorityRule {
                    rule: rule.clone(),
                    kind,
                    access,
                });
            }
        };

        push(&categories.deny_domains, RuleKind::Domain, Access::Deny);
        push(&categories.allow_domains, RuleKind::Domain, Access::Allow);
        push(&categories.deny_ips, RuleKind::Ip, Access::Deny);
        push(&categories.allow_ips, RuleKind::Ip, Access::Allow);
        push(&categories.deny_ip_ranges, RuleKind::IpRange, Access::Deny);
        push(
            &categories.allow_ip_ranges,
            RuleKind::IpRange,
            Access::Allow,
        );
        push(
            &categories.deny_url_patterns,
            RuleKind::UrlPattern,
            Access::Deny,
        );
        push(
            &categories.allow_url_patterns,
            RuleKind::UrlPattern,
            Access::Allow,
        );
        push(
            &categories.deny_protocol_rules,
            RuleKind::ProtocolRule,
            Access::Deny,
        );
        push(
            &categories.allow_protocol_rules,
            RuleKind::ProtocolRule,
            Access::Allow,
        );

        rules.sort_by_key(|r| r.rule.priority);

        Self { rules }
    }

    /// Evaluates `target` against this rule set in priority order,
    /// returning the first matching rule's access decision — the Rust
    /// port of `CheckAccess`'s matching loop (minus the per-call sort;
    /// see this type's doc). No matching rule → [`CheckOutcome::DeniedNoMatch`],
    /// matching the Go source's unconditional `return false` fallthrough
    /// (default deny).
    pub fn check(&self, target: &str) -> CheckOutcome {
        for pr in &self.rules {
            if matches_rule(&pr.rule, pr.kind, target) {
                return match pr.access {
                    Access::Allow => CheckOutcome::Allowed {
                        pattern: pr.rule.pattern.clone(),
                        priority: pr.rule.priority,
                    },
                    Access::Deny => CheckOutcome::DeniedByRule {
                        pattern: pr.rule.pattern.clone(),
                        priority: pr.rule.priority,
                    },
                };
            }
        }
        CheckOutcome::DeniedNoMatch
    }

    /// Total rule count across all ten categories.
    pub fn len(&self) -> usize {
        self.rules.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rules.is_empty()
    }
}

fn matches_rule(rule: &FirewallRule, kind: RuleKind, target: &str) -> bool {
    match kind {
        RuleKind::Domain => matcher::match_domain(&rule.pattern, target),
        RuleKind::Ip => matcher::match_ip(&rule.pattern, target),
        RuleKind::IpRange => matcher::match_ip_range(&rule.pattern, target),
        RuleKind::UrlPattern => matcher::match_url_pattern(&rule.pattern, target),
        RuleKind::ProtocolRule => matcher::match_protocol_rule(rule, target),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rule::RuleCategories;

    fn rule(pattern: &str, priority: i64) -> FirewallRule {
        FirewallRule {
            pattern: pattern.to_string(),
            priority,
            ..Default::default()
        }
    }

    fn user_rules(categories: RuleCategories) -> UserRules {
        UserRules {
            user_id: "user-1".to_string(),
            timestamp: "2026-01-01T00:00:00Z".to_string(),
            rules: categories,
        }
    }

    #[test]
    fn empty_rule_set_default_denies() {
        let set = RuleSet::build(&user_rules(RuleCategories::default()));
        assert!(set.is_empty());
        assert_eq!(set.check("example.com"), CheckOutcome::DeniedNoMatch);
        assert!(!set.check("example.com").allowed());
    }

    #[test]
    fn lower_priority_number_wins_regardless_of_insertion_order() {
        // A low-priority (= evaluated first) deny must win over a
        // higher-priority-number allow for the same pattern, even though
        // the allow rule was pushed into the deny_domains/allow_domains
        // split in Go's insertion order.
        let set = RuleSet::build(&user_rules(RuleCategories {
            deny_domains: vec![rule("example.com", 100)],
            allow_domains: vec![rule("example.com", 1)],
            ..Default::default()
        }));
        assert!(set.check("example.com").allowed());
    }

    #[test]
    fn equal_priority_ties_break_toward_deny_before_allow_same_category() {
        // Same priority, same category: Go's construction order pushes
        // deny_domains before allow_domains, and the bubble sort is
        // stable, so a tie keeps deny ahead of allow.
        let set = RuleSet::build(&user_rules(RuleCategories {
            deny_domains: vec![rule("example.com", 5)],
            allow_domains: vec![rule("example.com", 5)],
            ..Default::default()
        }));
        assert!(!set.check("example.com").allowed());
    }

    #[test]
    fn equal_priority_ties_break_by_go_category_insertion_order() {
        // Same priority, different categories, both able to match the
        // *same* target: `match_domain` is plain string equality (plus
        // wildcard), so a domain-category pattern of "10.0.0.1" matches
        // the literal target "10.0.0.1" exactly like an ip-category
        // pattern of "10.0.0.1" would. Go pushes deny/allow_domains
        // before deny/allow_ips, so at equal priority the domain rule
        // must be evaluated (and win) first.
        let set = RuleSet::build(&user_rules(RuleCategories {
            allow_domains: vec![rule("10.0.0.1", 5)],
            deny_ips: vec![rule("10.0.0.1", 5)],
            ..Default::default()
        }));
        assert!(set.check("10.0.0.1").allowed());
    }

    #[test]
    fn no_rules_in_any_category_is_default_deny_not_a_panic() {
        let set = RuleSet::build(&user_rules(RuleCategories::default()));
        assert_eq!(set.len(), 0);
        assert!(!set.check("anything.example.com").allowed());
    }

    #[test]
    fn first_matching_rule_in_priority_order_short_circuits_later_rules() {
        let set = RuleSet::build(&user_rules(RuleCategories {
            allow_domains: vec![rule("*.example.com", 1)],
            deny_domains: vec![rule("sub.example.com", 2)],
            ..Default::default()
        }));
        // Priority 1 (allow) is evaluated before priority 2 (deny), so
        // the more specific deny rule never gets a chance to run.
        assert!(set.check("sub.example.com").allowed());
    }

    #[test]
    fn deny_outcome_distinguishes_matched_rule_from_no_match() {
        let set = RuleSet::build(&user_rules(RuleCategories {
            deny_domains: vec![rule("example.com", 1)],
            ..Default::default()
        }));
        assert_eq!(
            set.check("example.com"),
            CheckOutcome::DeniedByRule {
                pattern: "example.com".to_string(),
                priority: 1,
            }
        );
        assert_eq!(set.check("other.com"), CheckOutcome::DeniedNoMatch);
    }
}
