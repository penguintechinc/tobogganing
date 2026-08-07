# Optional Analysis-Tool Sub-Charts (SASE Slice D)

Five out-of-band network/file analysis tools — **Suricata, Zeek, Arkime,
Strelka, CAPE** — ship as optional Helm sub-charts under `charts/`. They
are **off by default**: the baseline `tobogganing` chart deploys none of
them, and enabling one only stands up its pod + Service. This is the
first use of Helm's `dependencies:` + `condition:` mechanism in this
chart (see `Chart.yaml`).

> Not placed as `charts/README.md`: Helm's `dependency update`/`build`
> treats every entry directly under `charts/` as a subchart candidate and
> fails on anything without its own `Chart.yaml` (verified — a stray
> `.md` file there breaks `helm dependency update` with `Chart.yaml file
> is missing`). This note lives one level up instead.

## Flow

```
hub-router (Go mirror)            5 sub-charts (charts/, off by default)
  VXLAN/GRE/ERSPAN + direct   -->  Suricata / Zeek / Arkime / Strelka / CAPE
  TCP feed to Suricata              |
                                    v  writes EVE JSON / notice.log / API verdicts
                                hub-api adapter poller
                                (hub_api/modules/sase/security/adapters/)
                                    |
                                    v  normalize -> to_stix_indicator -> Verdict
                                BlocklistStore (sase:blocklist:*)
                                    |
                                    v  (Slice A contract — data-plane read side,
                                        out of scope for Slice D)
                                enforcement
```

Everything left of `BlocklistStore` is **strictly out-of-band**: adapters
read a mirror/log/API side-channel on a poll interval. Nothing in this
directory touches the live traffic path.

## Enabling a tool

Enabling `<tool>.enabled: true` (top-level key in the parent chart's
`values.yaml`) is necessary but not sufficient:

1. Deploy the sub-chart: `<tool>.enabled: true`.
2. Turn on the community-tier flag `tobogganing.sase.adapters` (default
   OFF — registered in the `sase` module contract as
   `Entitlement("sase.adapters", "community")`).
3. Point hub-api's adapter poller at the tool via the
   `{SOURCE}_ENABLED` / `{SOURCE}_ENDPOINT` / `{SOURCE}_LOG_PATH` env vars
   read by `hub_api/modules/sase/security/adapters/config.py`
   (`source` = `suricata|zeek|strelka|cape|arkime`), matching the
   `mirror.port` / `eve.logPath` / `frontend.port` / etc. values
   configured for that tool's sub-chart.

## Per-tool notes

| Tool | Image | Provenance | Port | Adapter wiring |
|---|---|---|---|---|
| Suricata | `jasonish/suricata:7.0.7` (SHA256-pinned) | Maintained by OISF core dev | 9999/TCP | Matches hub-router's existing `mirror.suricata_host`/`suricata_port` TCP feed — the one live wiring today |
| Zeek | `zeek/zeek:6.2.1` (SHA256-pinned) | Official Zeek Project image | mgmt port reserved (placeholder) | Log-based (`notice.log`); no live mirror source yet |
| Strelka | `target/strelka-frontend:1.0.1` (SHA256-pinned) | Target Corporation open source | 57314/TCP (gRPC) | Poller submits scans via gRPC |
| Arkime | **none — operator-supplied** | No maintained public image found (checked Docker Hub `itsarkime`, `ghcr.io/arkime/arkime`) | 8005/TCP (viewer) | Set `arkime.image.*` before enabling; render fails otherwise |
| CAPE | **none — operator-supplied** | Requires a hypervisor-backed sandbox host; not container-native | 8000/TCP (REST API) | Set `cape.image.*` before enabling; render fails otherwise |

**Suricata runs with a documented root exception** (`NET_ADMIN`/`NET_RAW`
for raw/AF_PACKET packet capture) mirroring the existing `hubRouter`
exception already present in the parent chart's `values.yaml` — see
`devops-containers.md` "Rootless Containers" exception process. All other
four tools use the standard non-root securityContext.

## Known integration gaps (by design — out of Slice D scope)

- **Shared log volume**: Suricata's `eve.json` and Zeek's `notice.log`
  are written to pod-local `emptyDir` volumes today. For hub-api's
  poller to read `SURICATA_LOG_PATH`/`ZEEK_LOG_PATH` in production, an
  operator needs to add a shared volume (e.g. an RWX PVC) mounted into
  both the tool pod and hub-api — not provisioned by this chart. The
  design doc calls this out explicitly as "a log volume with no consumer
  today — that volume is the seam."
- **NetworkPolicy**: the parent chart's default-deny + allow-internal
  `NetworkPolicy` selects pods by the `tobogganing.*` label helpers.
  These sub-charts use their own `app.kubernetes.io/name: <tool>` labels
  and are not yet covered by an explicit allow rule. Add one scoped to
  the tool's Service/port before relying on pod-to-pod traffic between
  hub-api and an enabled tool.
- **Zeek and Arkime are not wired to a live traffic mirror.** Only
  Suricata has direct `hub-router` mirror wiring today
  (`services/hub-router/proxy/mirror/manager.go`). Extending the Go
  mirror to the other tools is out of scope for Slice D.
