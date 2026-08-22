# W1 — testserver Engine Runs — Implementation Plan

- **Date:** 2026-08-21
- **Branch:** `fix/w1-testserver`
- **Spec:** `docs/superpowers/specs/2026-08-21-perftest-probe-suite-design.md` §Components item 2, Phases table row W1
- **Size:** S–M

## Scope

Three fixes to `engines/testserver` so the Helm chart on the sibling branch has something deployable:
1. GORM multi-DB (`DB_TYPE`: postgresql default / mysql / sqlite), remove `log.Fatalf` on DB failure
2. `ping`/`traceroute`/`tcptraceroute` binaries + `NET_RAW` in the runtime image
3. Verify: build, vet, test, docker build, docker run (no DB reachable + sqlite), probe binaries present

Out of scope: Helm chart (sibling branch owns it), h2/h3/new protocols (W3), schema/migration ownership mismatch between `engines/testserver`'s expected tables (`users`/`jwt_tokens`/`server_keys`/`server_test_results`) and `hub_api`'s actual Alembic schema (`perf_test_results`/`server_keys` with different columns, no `jwt_tokens`) — pre-existing, flag only, real fix is W2 (Check-in model: schema/migration).

## Task 1 — Pin GORM + drivers

- `engines/testserver/go.mod`: `go get` exact versions (no `@latest`):
  - `gorm.io/gorm@v1.31.2`
  - `gorm.io/driver/postgres@v1.6.2`
  - `gorm.io/driver/mysql@v1.6.0`
  - `gorm.io/driver/sqlite@v1.6.0` (mattn/go-sqlite3, cgo — Dockerfile already builds `CGO_ENABLED=1`)
  - Drop direct `github.com/go-sql-driver/mysql` (now pulled transitively by `gorm.io/driver/mysql`)
- Commit `go.mod`/`go.sum` together with the code changes (not standalone).

## Task 2 — `internal/database/database.go`: GORM + DB_TYPE + no fatal

Files: `engines/testserver/internal/database/database.go`

- `Config` gains `Type DBType` (`postgresql`|`mysql`|`sqlite`, default `postgresql`), keeps `Host/Port/User/Password/Database`.
- `DB` struct becomes `type DB struct { *gorm.DB }` (was `*sql.DB`).
- `New(cfg Config) (*DB, error)`: pick dialector by `Type`, `gorm.Open` with retry loop (5 attempts, 5s backoff, configurable via `Config.MaxRetries`/`RetryDelay`), pool via `sqlDB.SetMaxOpenConns/SetMaxIdleConns/SetConnMaxLifetime`. Returns error on exhaustion — caller (main.go) does NOT `log.Fatalf`.
- `ValidateAPIKey`/`ValidateJWT`/`ValidateServerKey`/`InsertTestResult` rewritten on GORM's query builder (`Where`/`Take`/`Create` — not raw SQL with hand-rolled `?`/`$1` placeholders, since GORM already dialect-translates placeholders and, critically, `Create()` handles per-dialect last-insert-id retrieval correctly — the old code's `res.LastInsertId()` would hard-fail on real Postgres).
- Add GORM row types (`jwtTokenJoinRow` internal, `serverKeyRecord`, `serverTestResultRow`) with `TableName()` matching existing table/column names (`users`, `jwt_tokens`, `server_keys`, `server_test_results`) — no schema change.
- `AutoMigrate` gated to `Type == sqlite` only (dev-tier per `backend-database.md`; postgres/mysql schema stays owned externally — do not migrate what we don't own).
- Compare `expires_at > NOW()` becomes `expires_at > ?` bound to `time.Now()` in Go — `NOW()` isn't portable to SQLite.

## Task 3 — `cmd/testserver/main.go`: env wiring + no fatal

- Add `DB_TYPE` (default `postgresql`), keep `DB_HOST`/`DB_PORT`(default `5432`, was `3306`)/`DB_USER`/`DB_PASS`/`DB_NAME` — matches `hub_api/config/__init__.py` env names.
- On `database.New` failure: `log.Printf` the error, start the HTTP server anyway with `db == nil`-safe handlers (health always up; auth middleware and result-save degrade with a clear 503/log rather than panic — `TestHandlers`/`Authenticator` already accept nil-safe interfaces via `NewWithStore`/`NewWithAuthDB`, wrap a small `nilDB`/error-returning stand-in when `db` is nil so handlers stay generic).

## Task 4 — Dockerfile: probe binaries + NET_RAW doc

File: `engines/testserver/Dockerfile`

- Runtime stage `apt-get install`: add `iputils-ping traceroute tcptraceroute` alongside `ca-certificates`, `--no-install-recommends`, `rm -rf /var/lib/apt/lists/*` (unchanged pattern).
- Fix the stale comment (`# ROOT EXCEPTION (approved): NET_RAW required...` currently sits right above `USER app` with no actual capability granted at the Dockerfile level — capabilities are a K8s securityContext concern, not Dockerfile). Replace with an accurate note that (a) the container itself stays non-root/rootless, (b) `NET_RAW` must be added via the K8s `securityContext.capabilities.add` on the sibling chart, not here.

## Task 5 — Tests

- `internal/database/database_mock_test.go`, `database_funcs_test.go`: rewrite for GORM — use `gorm.Open` against the `sqlmock`-provided `*sql.DB` via the postgres dialector's `Conn` option (`postgres.New(postgres.Config{Conn: mockDB})`), keep behavioral coverage (success/not-found/db-error/nil-pointer paths) for all 4 methods.
- Add `TestNew_DBTypeSelection` (table-driven over `postgresql`/`mysql`/`sqlite`/unknown) validating dialector selection without a live connection where feasible, plus a real sqlite round-trip test (`Type: sqlite, Database: ":memory:"`) exercising `ValidateAPIKey`/`InsertTestResult` end-to-end against `AutoMigrate`d tables.
- Add `TestNew_NoFatalOnUnreachable` confirming `New()` returns `(nil, err)` — never panics/exits — for an unreachable host with `MaxRetries: 1, RetryDelay: 1ms` (keep test fast).
- `cmd/testserver/main.go` currently untested (0% — pre-existing); add a minimal test for `getEnv` and the nil-DB degrade path if extracted into a testable helper.
- Coverage gate: `go test -cover ./...` ≥ 90% per package touched (`database`, `cmd/testserver`); `internal/protocols` (83% baseline) and `internal/handlers` (91%) are untouched by this phase — pre-existing protocols gap flagged to owner, not fixed here.

## Test cycle (run after each task, not just at the end)

```bash
cd engines/testserver
go build ./... && go vet ./...
go test ./... -race -cover
gofmt -s -l .   # must be empty
```

## Verification (Task 6, final)

```bash
cd engines/testserver
go build ./... && go vet ./...
go test ./... -race -cover

docker build -f Dockerfile --build-context proto=./proto \
  -t localhost:32000/tobogganing/testserver:alpha-local .

# binaries present
docker run --rm --entrypoint sh localhost:32000/tobogganing/testserver:alpha-local \
  -c "command -v ping traceroute tcptraceroute"

# runs without a reachable DB — must NOT exit
docker run -d --name w1-verify -p 18080:8080 -e DB_TYPE=sqlite -e DB_NAME=/tmp/testserver.db \
  localhost:32000/tobogganing/testserver:alpha-local
sleep 2
docker inspect -f '{{.State.Running}}' w1-verify   # must be "true"
curl -sf http://localhost:18080/health
docker rm -f w1-verify
```

No `| tail` on the exit-code-bearing commands — capture full output, check `$PIPESTATUS`/direct exit codes.

## Commit points

1. This plan doc — standalone commit.
2. `go.mod`/`go.sum` + `database.go` + `main.go` GORM conversion + tests — one commit (they're not independently buildable/testable split apart).
3. `Dockerfile` probe binaries + comment fix — can ride in the same commit as #2 per the task's single combined-commit instruction, or separately if the diff is reviewed piecemeal. Per task instructions: single combined commit `feat(testserver): GORM multi-DB (default postgres) + probe binaries + no fatal DB exit`.
