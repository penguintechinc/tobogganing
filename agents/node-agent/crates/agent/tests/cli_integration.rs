//! End-to-end exercise of the actual `node-agent` binary's `main()` —
//! process entry, structured-logging init, CLI parsing, and the two
//! `ExitCode` outcomes — via `std::process::Command`, the only way to
//! cover `main.rs` itself (a `#[tokio::main] async fn main` isn't
//! directly callable from a unit test).

use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_node-agent"))
}

#[test]
fn healthz_exits_zero_with_no_config_file() {
    let output = bin()
        .arg("healthz")
        .output()
        .expect("spawning the node-agent binary must succeed");
    assert!(
        output.status.success(),
        "expected healthz to exit 0 with default config; stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn healthz_exits_nonzero_on_a_malformed_config_file() {
    let dir = std::env::temp_dir().join(format!(
        "node-agent-cli-integration-test-{}",
        std::process::id()
    ));
    std::fs::create_dir_all(&dir).expect("temp dir must be creatable");
    let path = dir.join("config.toml");
    std::fs::write(&path, "mode = 12345\nnot valid = = toml{{{").expect("write must succeed");

    let output = bin()
        .arg("--config")
        .arg(&path)
        .arg("healthz")
        .output()
        .expect("spawning the node-agent binary must succeed");
    assert!(
        !output.status.success(),
        "a malformed config file must make the binary exit non-zero"
    );
    // `tracing_subscriber::fmt()` writes to stdout by default (no explicit
    // `.with_writer` override in `init_tracing`), so the structured error
    // log line lands there rather than on stderr.
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.contains("node-agent exited with an error"),
        "stdout must carry the structured error log line, got: {stdout}"
    );

    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn help_flag_exits_zero_without_running_anything() {
    let output = bin()
        .arg("--help")
        .output()
        .expect("spawning the node-agent binary must succeed");
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("node-agent"));
}
