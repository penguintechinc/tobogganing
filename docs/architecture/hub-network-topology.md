# Tobogganing — network topology

Data path: **client agent (laptop) → hub-client → hub-routers → resources**.
Control plane: **hub-api** is the brain (config + API); **hub-cli** and **hub-webui** are thin user overlays on top of it. Every client, hub, and bridge pulls its configuration from hub-api over **gRPC**.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'transparent','primaryColor':'#1e293b','primaryTextColor':'#e2e8f0','primaryBorderColor':'#475569','lineColor':'#94a3b8','fontFamily':'ui-monospace, SFMono-Regular, Menlo, monospace','fontSize':'14px','clusterBkg':'transparent','clusterBorder':'#334155'}}}%%
flowchart TB
  cli["hub-cli"]
  webui["hub-webui"]
  api["hub-api<br/>brains · config · API"]
  cli --> api
  webui --> api

  laptop["client agent<br/>laptop"]
  hubclient["hub-client<br/>WireGuard / OpenZiti receiver"]
  routers["hub-routers<br/>&ge;2 for production"]
  laptop ==> hubclient
  hubclient ==> routers

  subgraph resources["reachable resources"]
    direction LR
    vms["VMs<br/>client-node"]
    hw["hardware<br/>client-node"]
    k8s["k8s nodes<br/>client-k8s"]
    svcs["services"]
    perf["hub-perf<br/>test receivers"]
  end
  routers ==> vms
  routers ==> hw
  routers ==> k8s
  routers ==> svcs
  routers ==> perf

  api -.-> laptop
  api -.-> hubclient
  api -.-> routers
  api -.-> vms
  api -.-> hw
  api -.-> k8s
  api -.-> perf

  classDef brain fill:#fbbf24,stroke:#b45309,color:#1c1917;
  classDef overlay fill:#0f172a,stroke:#fbbf24,color:#fbbf24;
  classDef hub fill:#0ea5e9,stroke:#0369a1,color:#04263a;
  classDef client fill:#334155,stroke:#94a3b8,color:#e2e8f0;
  classDef res fill:#111c30,stroke:#334155,color:#cbd5e1;
  class api brain;
  class cli,webui overlay;
  class hubclient,routers hub;
  class laptop client;
  class vms,hw,k8s,svcs,perf res;
```

**Legend** — solid thick = data path (traffic); dotted = configuration via gRPC.

## How to read it

- **Data plane:** the laptop client agent connects into **hub-client** (WireGuard/OpenZiti receiver for end-user clients), which hands off to the **hub-routers**; from there it reaches VMs, hardware, k8s nodes, and services.
- **Control plane:** **hub-cli** and **hub-webui** are thin overlays on **hub-api** for configuration, management, and review — no business logic of their own. hub-webui is today's React portal; hub-cli is new.
- **Config over gRPC:** every client, hub, and bridge fetches its configuration from hub-api via gRPC — hub-api is the single source of truth.
- **Redundancy:** production requires **≥2 hub-routers**; a single hub-router is flagged "not production ready."
- **Per-user transport:** WireGuard vs OpenZiti is chosen per end-user in hub-api and delivered to the penguin agent as a config file.

See `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md` for the full target architecture and phasing.
