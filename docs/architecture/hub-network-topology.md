# Tobogganing — network topology

Data path: **client agent (laptop) → hub-client (front door) → hub-routers → resources**; agentless / external targets via **bridge-router** (Enterprise).
Control plane: **hub-api** is the brain; **hub-cli** and **hub-webui** are thin overlays. Every client, hub, and bridge pulls its configuration from hub-api over **gRPC**. The two **Inspection Points** (hub-client, bridge-router) tap Suricata / Zeek / Arkime for alerts + block verdicts.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'transparent','primaryColor':'#1e293b','primaryTextColor':'#e2e8f0','primaryBorderColor':'#475569','lineColor':'#94a3b8','fontFamily':'ui-monospace, SFMono-Regular, Menlo, monospace','fontSize':'13px','clusterBkg':'transparent','clusterBorder':'#334155'}}}%%
flowchart TB
  cli["hub-cli"]
  webui["hub-webui"]
  api["hub-api<br/>brains · config · API"]
  cli --> api
  webui --> api

  laptop["client agent<br/>laptop"]
  hubclient["hub-client — FRONT DOOR<br/>primary: WG / OpenZiti<br/>fallback: OpenVPN-443 / IPsec-MOBIKE"]
  routers["hub-routers<br/>lightweight · &ge;2 for prod"]
  bridge["bridge-router (Enterprise)<br/>transit hub + SASE PEP"]

  laptop ==> hubclient
  hubclient ==> routers

  subgraph agentnodes["agent nodes → hub-routers"]
    direction LR
    k8s["k8s nodes<br/>client-k8s"]
    vms["VMs<br/>client-node"]
    hw["hardware<br/>client-node"]
    perf["hub-perf<br/>test receivers"]
  end
  routers ==> k8s
  routers ==> vms
  routers ==> hw
  routers ==> perf

  subgraph external["agentless / external → bridge-router"]
    direction LR
    svcs["services"]
    extnet["external nets<br/>VPCs · sites"]
  end
  routers ==> bridge
  bridge ==> svcs
  bridge ==> extnet

  subgraph sensors["monitoring tap"]
    direction LR
    suricata["Suricata<br/>IDS/IPS"]
    zeek["Zeek<br/>NSM"]
    arkime["Arkime<br/>capture"]
  end
  hubclient -->|tap + verdict| sensors
  bridge -->|tap + verdict| sensors

  api -.-> laptop
  api -.-> hubclient
  api -.-> routers
  api -.-> bridge

  classDef brain fill:#fbbf24,stroke:#b45309,color:#1c1917;
  classDef overlay fill:#0f172a,stroke:#fbbf24,color:#fbbf24;
  classDef inspect fill:#0ea5e9,stroke:#fbbf24,color:#04263a,stroke-width:2px;
  classDef hub fill:#0ea5e9,stroke:#0369a1,color:#04263a;
  classDef client fill:#334155,stroke:#94a3b8,color:#e2e8f0;
  classDef res fill:#111c30,stroke:#334155,color:#cbd5e1;
  classDef sensor fill:#4c1d24,stroke:#f43f5e,color:#fecdd3;
  class api brain;
  class cli,webui overlay;
  class hubclient,bridge inspect;
  class routers hub;
  class laptop client;
  class k8s,vms,hw,perf,svcs,extnet res;
  class suricata,zeek,arkime sensor;
```

**Legend** — thick = data path (traffic) · dotted = config via gRPC (also to every node agent & hub-perf) · thin = sensor tap + block verdict · amber-bordered node = Inspection Point.

## How to read it

- **Front door (hub-client):** end-user access lands here — primary WireGuard/OpenZiti, auto-falling back to OpenVPN-over-443 or IPsec/MOBIKE on restrictive networks. Also terminates contractors, vendor/customer S2S IPsec, and (future) Apache Guacamole clientless. Everything is inspected before the fabric.
- **Fabric (hub-routers):** lightweight c2c transport + node relay — basic policy + auth only. ≥2 for production (warn on 1). Agent nodes (client-k8s / client-node) connect here directly.
- **Bridge (bridge-router, Enterprise):** transit/interconnect hub (GCP NCC / AWS TGW-style) + SASE PEP for agentless services and external nets / VPCs / sites.
- **Inspection Points (hub-client + bridge-router):** customized proxy (Envoy+Rust filters *or* custom Rust/Go — TBD) that taps Suricata (IDS/IPS), Zeek (NSM), and Arkime (capture), which return alerts + inline block verdicts.
- **Control plane:** hub-cli + hub-webui are thin overlays on hub-api; every client/hub/bridge pulls config from hub-api via gRPC (single source of truth).
- **Out of scope:** intra-cluster k8s east-west security (Cilium NetworkPolicy / admission / Tetragon) — owned by the Gough project. Tobogganing owns the true network/overlay layer.

See `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md` for the full target architecture, enrollment/connect-token model, and phasing.
