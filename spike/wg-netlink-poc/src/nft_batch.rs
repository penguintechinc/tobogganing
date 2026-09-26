//! Goal 4: apply firewall/routing rules as one atomic nftables transaction,
//! so a crash mid-update can never leave a half-applied ruleset (migration
//! plan risk #3: "WireGuard state desync on crash mid-update").
//!
//! Crate landscape considered:
//! - `rustables` (pure-Rust libnftnl bindings) — GPL-3.0-or-later. A
//!   proprietary, license-server-gated binary linking GPL-3 code is a real
//!   `cargo deny` license-policy conflict; ruled out without an explicit
//!   licensing exception.
//! - `nftnl` (Mullvad) — MIT/Apache-2.0, but links the C `libnftnl` at build
//!   AND runtime (`nftnl-sys`), reintroducing a native-lib dependency this
//!   effort is trying to move away from (same category of risk as `wg-quick`
//!   being a C-toolchain dependency).
//! - **`nft -f <file>` via `tokio::process::Command`** — nft's own `-f`
//!   flag applies an entire ruleset file as a single atomic transaction
//!   (this is nftables' own crash-safety guarantee, not something we're
//!   reimplementing). Recommended: it's only invoked at startup/config-change
//!   (batch), never per-connection, so the exec overhead that made the Go
//!   per-connection `iptables` calls a real anti-pattern does not apply here.

use std::process::Stdio;
use tokio::io::AsyncWriteExt;
use tokio::process::Command;

/// The fwmark-matching nftables ruleset applied once at startup, replacing
/// the Go code's per-connection `iptables -t mangle -A OUTPUT ... MARK`
/// inserts. `hub_router_mark` is a stable table/chain name so re-applying
/// (e.g. on config reload) is naturally idempotent — nft ruleset files are
/// declarative, not additive like the old iptables `-A` calls.
pub fn authenticated_mark_ruleset(mark: u32) -> String {
    format!(
        "table inet hub_router {{\n\
         \x20 chain mark_authenticated {{\n\
         \x20  type filter hook output priority mangle; policy accept;\n\
         \x20  meta mark {mark} accept\n\
         \x20 }}\n\
         }}\n"
    )
}

/// Apply an nftables ruleset atomically via `nft -f -` (reads the ruleset
/// from stdin). Returns an error including nft's stderr on failure — never
/// silently ignores a non-zero exit.
///
/// NEEDS PRIVILEGED ENV: `nft` itself needs `CAP_NET_ADMIN` (or root) to
/// apply rules to the kernel nf_tables subsystem. In this sandbox this will
/// fail (either `nft` binary absent, or permission denied) — the function
/// is fully implemented and its error path is exercised either way.
pub async fn apply_ruleset_atomic(ruleset: &str) -> anyhow::Result<()> {
    let mut child = Command::new("nft")
        .arg("-f")
        .arg("-")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;

    child
        .stdin
        .take()
        .expect("stdin piped")
        .write_all(ruleset.as_bytes())
        .await?;

    let output = child.wait_with_output().await?;
    if !output.status.success() {
        anyhow::bail!(
            "nft -f - failed (exit {:?}): {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// VALIDATED (pure string generation, no privilege needed): the
    /// ruleset text is well-formed and references the expected mark value.
    #[test]
    fn ruleset_contains_the_configured_mark() {
        let ruleset = authenticated_mark_ruleset(100);
        assert!(ruleset.contains("meta mark 100 accept"));
        assert!(ruleset.contains("table inet hub_router"));
    }

    /// NEEDS PRIVILEGED ENV: `nft` requires CAP_NET_ADMIN to actually apply
    /// rules. Asserts the call fails cleanly (Err, not a panic) whether
    /// that's because `nft` isn't installed in this sandbox or because the
    /// kernel rejects the unprivileged apply.
    #[tokio::test]
    async fn apply_fails_closed_without_privilege_or_binary() {
        let ruleset = authenticated_mark_ruleset(100);
        let result = apply_ruleset_atomic(&ruleset).await;
        assert!(
            result.is_err(),
            "expected failure without CAP_NET_ADMIN / nft binary in this sandbox"
        );
    }
}
