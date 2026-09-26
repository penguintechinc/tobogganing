//! Shared subprocess-execution helper for the shell-out probe family
//! (ICMP/traceroute — `icmp.rs`/`trace.rs`), ported from
//! `engines/testserver/internal/protocols/icmp.go` and `trace.go`. Both Go
//! sources shell out to the system `ping`/`traceroute`/`tcptraceroute`
//! binaries and regex-parse stdout — **not** raw ICMP sockets. This module
//! isolates the one part of that port that actually touches a real
//! subprocess (`run_command`), so every output-parsing function in
//! `icmp.rs`/`trace.rs` stays a pure, synchronous function that unit tests
//! exercise on captured fixture text, never a real `ping`/`traceroute`
//! binary — see those modules' `#[cfg(test)]` blocks.

/// Result of running a subprocess: exit success plus stdout/stderr kept
/// separate (some Go call sites use `CombinedOutput()`, others read the two
/// streams independently and fall back to stderr only when stdout is
/// empty — see `combined`/`stdout_or_stderr` below).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub(crate) struct CommandOutput {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
}

impl CommandOutput {
    /// Mirrors `icmp.go`'s `cmd.CombinedOutput()` — approximated as stdout
    /// followed by stderr (true fd-level interleaving isn't available
    /// through `tokio::process::Command`'s `.output()`, but ping/traceroute
    /// write their parseable data to stdout, so this is behaviorally
    /// equivalent for parsing purposes).
    pub(crate) fn combined(&self) -> String {
        if self.stderr.is_empty() {
            self.stdout.clone()
        } else {
            format!("{}{}", self.stdout, self.stderr)
        }
    }

    /// Mirrors `trace.go`'s repeated `output := stdout.String(); if output
    /// == "" { output = stderr.String() }` pattern.
    pub(crate) fn stdout_or_stderr(&self) -> String {
        if self.stdout.is_empty() {
            self.stderr.clone()
        } else {
            self.stdout.clone()
        }
    }
}

/// Runs `program` with `args` via `tokio::process::Command`, capturing
/// stdout/stderr. A spawn failure (binary not found, no permission, etc.)
/// is folded into `success: false` with the error text in `stderr` — same
/// shape as a command that ran and exited non-zero, so callers have one
/// failure path to handle, matching how `cmd.Run()`'s `error` return is
/// used in the Go source.
pub(crate) async fn run_command(program: &str, args: &[String]) -> CommandOutput {
    match tokio::process::Command::new(program)
        .args(args)
        .output()
        .await
    {
        Ok(output) => CommandOutput {
            success: output.status.success(),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        },
        Err(e) => CommandOutput {
            success: false,
            stdout: String::new(),
            stderr: format!("failed to execute {program}: {e}"),
        },
    }
}

/// Port of Go's `exec.LookPath(program)` existence check (`trace.go` uses
/// this to prefer `tcptraceroute` over `traceroute -T` when available). Only
/// checks presence on `PATH`, not the executable bit — an approximation
/// acceptable here because the actual `run_command` call is always the
/// final arbiter of whether the program could really be executed.
pub(crate) fn command_exists(program: &str) -> bool {
    std::env::var_os("PATH")
        .is_some_and(|paths| std::env::split_paths(&paths).any(|dir| dir.join(program).is_file()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn combined_prefers_stdout_then_appends_stderr() {
        let out = CommandOutput {
            success: true,
            stdout: "line1\n".into(),
            stderr: "warn\n".into(),
        };
        assert_eq!(out.combined(), "line1\nwarn\n");
    }

    #[test]
    fn combined_is_just_stdout_when_stderr_empty() {
        let out = CommandOutput {
            success: true,
            stdout: "line1\n".into(),
            stderr: String::new(),
        };
        assert_eq!(out.combined(), "line1\n");
    }

    #[test]
    fn stdout_or_stderr_falls_back_only_when_stdout_empty() {
        let out = CommandOutput {
            success: false,
            stdout: String::new(),
            stderr: "boom".into(),
        };
        assert_eq!(out.stdout_or_stderr(), "boom");

        let out = CommandOutput {
            success: true,
            stdout: "ok".into(),
            stderr: "ignored".into(),
        };
        assert_eq!(out.stdout_or_stderr(), "ok");
    }

    #[tokio::test]
    async fn run_command_reports_failure_for_nonexistent_binary_without_panicking() {
        // No real ping/traceroute dependency: a binary name that can't
        // possibly exist deterministically exercises the spawn-failure path.
        let result = run_command(
            "testserver-rs-definitely-not-a-real-binary",
            &["--help".to_string()],
        )
        .await;
        assert!(!result.success);
        assert!(!result.stderr.is_empty());
    }

    #[test]
    fn command_exists_is_false_for_bogus_binary_name() {
        assert!(!command_exists(
            "testserver-rs-definitely-not-a-real-binary"
        ));
    }
}
