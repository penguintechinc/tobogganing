# testserver-rs workspace Makefile — mirrors the org convention (root
# Makefile's per-language targets) scoped to this Cargo workspace. Every
# target here is a real gate: none are wrapped in `|| true`, so a failing
# check fails the target (see critical-rules.md Verification Integrity).

.PHONY: build test fmt fmt-check clippy deny coverage smoke-telemetry lint pre-push

build: ## Build every crate + test target in the workspace
	cargo build --workspace --all-targets

test: ## Run the full workspace test suite (unit + integration)
	cargo test --workspace

fmt: ## Reformat in place
	cargo fmt

fmt-check: ## Gate: cargo fmt --check must be clean
	cargo fmt --check

clippy: ## Gate: clippy clean, warnings denied
	cargo clippy --all-targets -- -D warnings

deny: ## Gate: advisories (RustSec), license policy, banned/duplicate crates
	cargo deny check

# cargo-llvm-cov has no stable `--fail-under-branches` flag (`--branch` is
# nightly-only/unstable) — region coverage is used as the branch-coverage
# proxy per testing-rust.md, and is strictly finer-grained than branch
# counting (every distinct code region, not just true/false branch arms).
coverage: ## Gate: fails below 90% lines/regions/functions — never `|| true`
	cargo llvm-cov --workspace \
		--fail-under-lines 90 \
		--fail-under-regions 90 \
		--fail-under-functions 90

smoke-telemetry: ## Telemetry-validation smoke test (OTLP logs/metrics/histograms) — prints counts, never a bare pass/fail
	cargo test --test telemetry_smoke -- --nocapture

lint: fmt-check clippy

# Wired into .pre-commit-config.yaml as a `stages: [pre-push]` local hook
# scoped to this directory — coverage is a real gate on `git push`, not
# just a number computed at merge time.
pre-push: lint deny coverage
