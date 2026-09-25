# Phase 6 — >1000-Line Files + Hardening Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the program's last phase: split `services/hub-router/proxy/main.go` (1329 lines) into cohesive ≤1000-line files, re-enable the two disabled Go tests, enforce TLS MinVersion 1.2 on every `tls.Config`, verify default-deny NetworkPolicy, and remove the dead `shared/react_libs` fork.

**Scope corrections vs the umbrella plan:** `FormModalBuilder.tsx` (1081) lives only in the stale unused `shared/react_libs` fork (v1.1.0; published `@penguintechinc/react-libs` is 1.3.5; zero in-repo consumers) — deleting the fork per the no-local-shared-copies standard supersedes splitting it. All Python core files are already <1000 lines.

**Global constraints:** Go 1.25 in Docker (`golang:1.25-bookworm`) for build/test if no local toolchain; behavior-preserving refactor only; gofmt + `go vet`; never delete/skip a test; branch `feature/phase-6-hardening` off `feature/phase-5b-portal-views`.

### Task 1: hub-router main.go split (Go)
Split `services/hub-router/proxy/main.go` into: `bootstrap.go` (config/flags/startup wiring), `http_handlers.go`, `tcp_proxy.go`, `udp_proxy.go`, `dynamic_ports.go` — same package, no API changes; extract the duplicated JWT-validation and target packet-parse helpers into `helpers.go` (single implementation). Find the two disabled tests (commented-out, `t.Skip`, or renamed `Xtest`) and re-enable them, fixing whatever made them fail. Audit every `tls.Config` in `services/hub-router` for `MinVersion: tls.VersionTLS12`. Verify: `go build ./...` + `go vet ./...` + `go test ./... -count=1` green (Docker if needed), each file ≤1000 lines, `gofmt -l` empty.

### Task 2: dead fork removal + NetworkPolicy (orchestrator)
`git rm -r shared/react_libs` (confirm zero imports first); verify `k8s/helm/tobogganing/templates/networkpolicy.yaml` implements default-deny ingress with same-namespace allow (fix if not); `helm lint` if available.

### Task 3: verification + PR
Full core pytest suite + portal jest gate still green (no cross-impact expected); commit groups; push; stacked PR base `feature/phase-5b-portal-views`; memory + task list updates.
