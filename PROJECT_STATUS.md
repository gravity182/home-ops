# Homelab Migration Project - Status & Context

## Project Overview

**Goal:** Migrate existing homeserver to a modern Flux GitOps setup using onedr0p's cluster-template as foundation.

**Domain:** jellywatch.dev (managed in Cloudflare)
**Timezone:** Europe/Moscow
**UID/GID:** 1000:1000

## Target Architecture

- **OS:** Talos Linux (immutable, Kubernetes-native)
- **GitOps:** Flux CD v2
- **CNI:** Cilium (eBPF-based networking)
- **Ingress:** Envoy Gateway (replaces Traefik)
- **Storage:** OpenEBS LocalPV-HostPath (single node)
- **Secrets:** SOPS + Age encryption
- **DNS:** External-DNS + Cloudflare
- **Public Access:** Cloudflare Tunnel
- **Auth:** Authentik SSO
- **VPN:** WireGuard sidecar component (reusable)

## Hardware Setup

**Node:** Beelink Mini PC
- **Hostname:** homeserver-main
- **IP:** 192.168.3.26
- **MAC:** e8:ff:1e:df:0a:bd
- **Disk:** /dev/sda (512GB SSD)
- **Network:** 192.168.3.0/24
- **Gateway:** 192.168.3.1

**Kubernetes Network:**
- **API VIP:** 192.168.3.100:6443
- **DNS Gateway:** 192.168.3.101
- **Internal Gateway:** 192.168.3.102
- **External Gateway:** 192.168.3.103 (Cloudflare)
- **Pod CIDR:** 10.42.0.0/16
- **Service CIDR:** 10.43.0.0/16

## Key Architectural Decisions

1. **Storage:** OpenEBS LocalPV-HostPath (single node, no dedicated disks)
   - Uses `/var/openebs-system/local` with Talos kubelet extraMount
   - Talos extraMount at `/var/openebs-system` with bind, rshared, rw options
   - CNCF graduated project with snapshot support
   - OpenEBS 4.4.0 with observability stack disabled

2. **VPN:** WireGuard sidecar component (portable, no network infrastructure changes)
   - Reusable Kustomize component at `kubernetes/components/vpn-sidecar/`
   - Uses lscr.io/linuxserver/wireguard image
   - Secrets stored as SOPS-encrypted Kubernetes Secrets

3. **Secrets:** SOPS + Age encryption (simpler than ExternalSecrets)
   - Age key stored at repository root: `age.key`
   - Public key: age1kaeupmjdqc74w54956ryp02x4tfautx7yp8z22sh6jp30408jphqz5tdc6

4. **Auth:** Authentik as infrastructure component (deploy before apps)
   - PostgreSQL + Redis as subcharts
   - Forward auth with Envoy Gateway SecurityPolicy

5. **Fresh Start:** New configs, restore backups later manually

## Repository Structure

```
/Users/dmitryalexandrov/IdeaProjects/private/homeserver-v2/
├── .sops.yaml                          # SOPS encryption config
├── age.key                             # SOPS encryption key (DO NOT COMMIT)
├── cluster.yaml                        # Cluster configuration
├── nodes.yaml                          # Node specifications
├── cloudflare-tunnel.json              # Cloudflare tunnel credentials
├── github-deploy.key / .pub            # GitHub deploy keys
├── kubeconfig                          # Kubernetes credentials (generated after bootstrap)
├── talos/
│   ├── talconfig.yaml                  # Talos configuration (generated from cluster.yaml/nodes.yaml)
│   ├── talconfig.yaml.backup           # Backup of full config
│   ├── talconfig.yaml.full             # Full config with all patches
│   ├── talsecret.sops.yaml             # Encrypted Talos secrets
│   ├── clusterconfig/                  # Generated Talos machine configs
│   └── patches/
│       └── global/
│           ├── machine-disk-wipe.yaml        # wipe: true for installation
│           ├── machine-insecure-registry.yaml # Mirror factory.talos.dev to local registry
│           ├── machine-files.yaml
│           ├── machine-kubelet.yaml
│           ├── machine-network.yaml
│           ├── machine-sysctls.yaml
│           └── machine-time.yaml
└── kubernetes/
    ├── apps/                           # Applications (to be created)
    ├── components/                     # Reusable components
    │   └── vpn-sidecar/               # (to be created)
    └── flux/                          # Flux configuration
```

## GitHub Repository

**Name:** gravity182/home-ops
**URL:** https://github.com/gravity182/home-ops
**Branch:** main
**Visibility:** public

## Critical Apps to Migrate (Phase 5)

1. **radarr** (no VPN) - Movies
2. **sonarr** (no VPN) - TV shows
3. **prowlarr** (with VPN) - Indexer management
4. **qbittorrent** (with VPN) - Torrent client
5. **sabnzbd** (no VPN) - Usenet client
6. **jellyfin** (no VPN) - Media server

## Migration Phases

### Phase 1: Bootstrap Cluster Foundation ✅ COMPLETE

**Status:** COMPLETE

**Completed:**
- ✅ Repository initialized from cluster-template
- ✅ Talos OS installed on Beelink (resolved architecture issue with local registry)
- ✅ Kubernetes cluster bootstrapped (v1.35.0)
- ✅ Flux deployed and syncing from GitHub
- ✅ Core infrastructure running (Cilium, CoreDNS, Envoy Gateway, cert-manager)
- ✅ Talos configuration committed to GitHub

### Phase 2: Storage Layer ✅ COMPLETE

**Goal:** Deploy OpenEBS LocalPV-HostPath

**Completed:**
- ✅ Created storage app structure at `kubernetes/apps/kube-system/openebs/`
- ✅ Deployed OpenEBS 4.4.0 via Flux HelmRelease
- ✅ Disabled observability stack (Loki, Minio, Alloy)
- ✅ Configured Talos kubelet extraMount for `/var/openebs-system`
- ✅ Set openebs-hostpath as default StorageClass
- ✅ Verified PVC creation works with Authentik PostgreSQL

### Phase 3: VPN Sidecar Component ✅ COMPLETE

**Goal:** Create reusable Kustomize component for WireGuard VPN sidecars

**Completed:**
- ✅ Created component at `kubernetes/components/vpn-sidecar/`
- ✅ Created deployment patch for wireguard sidecar
- ✅ Configured NET_ADMIN capabilities and sysctls
- ✅ SOPS-encrypted WireGuard NL configuration
- ✅ Local network routing preserved (192.168.x, 10.x, 172.16.x)

### Phase 4: Authentik Authentication ✅ COMPLETE

**Goal:** Deploy Authentik SSO before media apps

**Completed:**
- ✅ Created namespace and app structure
- ✅ Deployed Authentik with PostgreSQL + Redis subcharts
- ✅ OpenEBS storage working with openebs-hostpath StorageClass
- ✅ Authentik accessible and operational

### Phase 5: Critical Apps Deployment ⏳ IN PROGRESS

**Goal:** Deploy 6 critical apps

**Order:**
1. radarr (no VPN) - validate pattern
2. sonarr (no VPN) - confirm pattern
3. sabnzbd (no VPN) - Usenet client
4. prowlarr (with VPN) - first VPN test
5. qbittorrent (with VPN) - second VPN validation
6. jellyfin (media server) - user-facing

**Progress:**
- ⏳ Ready to begin deployment

### Phase 6: Monitoring Stack (NOT STARTED - OPTIONAL)

**Goal:** Deploy observability stack

**Tasks:**
- Deploy kube-prometheus-stack
- Configure Grafana with Authentik OAuth
- Add Loki for log aggregation
- Create custom dashboards

### Phase 7: Testing & Validation (NOT STARTED)

**Goal:** Comprehensive testing of all components

## Current Status: Phase 5 In Progress

### What's Working

✅ Talos Linux cluster running (v1.12.1)
✅ Kubernetes running (v1.35.0)
✅ Flux GitOps syncing from GitHub
✅ Cilium CNI operational
✅ Envoy Gateway for ingress
✅ OpenEBS storage provisioner deployed (openebs-hostpath)
✅ VPN sidecar component ready
✅ Authentik deployed and operational

### Current Task: Deploy Critical Media Apps

**Task:** Deploy the 6 critical media apps starting with radarr

**Deployment Order:**
1. **radarr** (no VPN) - First deployment to validate the pattern
2. **sonarr** (no VPN) - Confirm the pattern works
3. **sabnzbd** (no VPN) - Usenet client
4. **prowlarr** (with VPN) - First app with VPN sidecar
5. **qbittorrent** (with VPN) - Second VPN validation
6. **jellyfin** (no VPN) - Media server for end users

**App Structure Pattern:**
```
kubernetes/apps/media/
├── namespace.yaml
├── kustomization.yaml
├── radarr/
│   ├── ks.yaml
│   └── app/
│       ├── kustomization.yaml
│       ├── helmrelease.yaml
│       └── secret.sops.yaml (if needed)
```

**Key Requirements:**
- Use bjw-s app-template chart
- Configure persistent storage with OpenEBS
- Reference old homeserver configs for app-specific settings
- VPN apps use the vpn-sidecar component
- Consider Authentik forward auth integration

## Important Files & Credentials

### Encryption Keys
- **Age Key:** `age.key` (repository root) - **DO NOT COMMIT**
- **Age Public Key:** age1kaeupmjdqc74w54956ryp02x4tfautx7yp8z22sh6jp30408jphqz5tdc6

### GitHub
- **Deploy Key:** `github-deploy.key` + `.pub`
- **Push Token:** `github-push-token.txt`

### Cloudflare
- **API Token:** Stored in `cluster.yaml` (line 64)
- **Tunnel Credentials:** `cloudflare-tunnel.json`
- **Tunnel Name:** kubernetes

### Talos
- **Schematic ID:** 039535a70c3bd1667c355eca78571267704e55c8a24785033d183b8f26e39d82
- **Talos Version:** v1.12.1
- **Kubernetes Version:** v1.35.0

## Key Commands

### Talos Bootstrap
```bash
cd /Users/dmitryalexandrov/IdeaProjects/private/homeserver-v2

# Full bootstrap (currently fails at installation)
task bootstrap:talos

# Manual apply config
cd talos
talosctl apply-config --talosconfig=./clusterconfig/talosconfig --nodes 192.168.3.26 --file=./clusterconfig/kubernetes-homeserver-main.yaml --insecure

# After successful install, bootstrap K8s
task bootstrap:apps
```

### Check Node Status
```bash
# From maintenance mode (before install)
talosctl get disks --nodes 192.168.3.26 --insecure
talosctl get links --nodes 192.168.3.26 --insecure

# After install (with talosconfig)
talosctl get machinestatus --nodes 192.168.3.26 --talosconfig=./talos/clusterconfig/talosconfig
talosctl services --nodes 192.168.3.26 --talosconfig=./talos/clusterconfig/talosconfig
```

### Local Registry
```bash
# Check registry
curl http://localhost:5001/v2/_catalog

# View Docker images
docker images | grep talos

# Push new image
docker tag <source> localhost:5001/<path>:<tag>
docker push localhost:5001/<path>:<tag>
```

### Flux Management (after Phase 1 complete)
```bash
# Check Flux status
flux get all -A

# Force reconcile
flux reconcile source git flux-system
flux reconcile ks cluster-apps
```

## References

### Documentation
- **Onedr0p Cluster Template:** https://github.com/onedr0p/cluster-template
- **Talos Docs:** https://www.talos.dev/
- **OpenEBS Docs:** https://openebs.io/docs
- **bjw-s app-template:** https://bjw-s.github.io/helm-charts/docs/app-template/
- **Flux Docs:** https://fluxcd.io/flux/

### Reference Repos
- **Old Homeserver (SOURCE FOR MIGRATION):** `/Users/dmitryalexandrov/IdeaProjects/private/homeserver`
  - **Main Config:** `values.extend.yaml` - Production app configurations
  - **VPN Pattern:** `templates/_vpn.tpl` - WireGuard sidecar implementation
  - **Authentik Setup:** `templates/authentik/` - Auth deployment configs
  - **Key Apps Config Lines:**
    - qbittorrent: lines 599-616 (with VPN)
    - radarr: lines 668-683 (no VPN)
- **Onedr0p Cluster Template:** `/Users/dmitryalexandrov/IdeaProjects/private/onedr0p-cluster-template`
  - Bootstrap process reference
  - Makejinja templating examples
- **Onedr0p Personal Repo:** `/Users/dmitryalexandrov/IdeaProjects/private/onedr0p-home-ops`
  - **Modern arr-stack patterns:** `kubernetes/apps/default/radarr/`
  - **VPN integration (Multus):** `kubernetes/apps/default/qbittorrent/`
  - **Reusable components:** `kubernetes/components/volsync/`
  - **Monitoring setup:** `kubernetes/apps/observability/`

### Detailed Plan
- **Full Implementation Plan:** `/Users/dmitryalexandrov/.claude/plans/purring-beaming-comet.md`

## Critical Context for Next Session

1. **Infrastructure is ready** - Talos, Kubernetes, Flux, OpenEBS, VPN sidecar, Authentik all operational
2. **Local registry is running** at 192.168.3.25:5001 (mirrors factory.talos.dev)
3. **All configs are committed to git** and managed by Flux
4. **Fresh start approach** - no data migration, backups will be restored manually later
5. **VPN sidecar component** ready at `kubernetes/components/vpn-sidecar/`

## Next Actions (Priority Order)

1. **Deploy radarr** (no VPN) - First media app to validate pattern
   - Create namespace `media`
   - Set up app structure following onedr0p pattern
   - Use bjw-s app-template chart
   - Reference old homeserver config for app settings

2. **Deploy sonarr** (no VPN) - Confirm pattern works

3. **Deploy sabnzbd** (no VPN) - Usenet client

4. **Deploy prowlarr** (with VPN) - First VPN sidecar test
   - Validate vpn-sidecar component integration
   - Verify VPN connectivity

5. **Deploy qbittorrent** (with VPN) - Second VPN app

6. **Deploy jellyfin** (no VPN) - User-facing media server

## Lessons Learned

1. **Port 5000 blocked by AirPlay on macOS** - Use port 5001 for Docker registry
2. **factory.talos.dev can be unreachable** - Local registry mirror is necessary
3. **`wipe: false` by default** - Need explicit `wipe: true` patch for fresh installs
4. **Talos uses HTTPS for registries by default** - Need `http://` prefix in mirror endpoints
5. **VIP configuration is intentional** - 192.168.3.100 for HA even on single node
6. **OpenEBS 4.4.0 includes observability stack** - Loki, Minio, Alloy enabled by default, must explicitly disable
7. **OpenEBS basePath** - Use `/var/openebs-system/local` for LocalPV HostPath storage

---

**Last Updated:** 2026-01-07
**Current Phase:** Phase 5 (Critical Apps Deployment) - IN PROGRESS
**Next Step:** Deploy radarr as first media app to validate the deployment pattern
