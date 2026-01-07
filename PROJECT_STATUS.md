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
   - Uses `/var/openebs/local` (writable on Talos by default)
   - No Talos extraMounts needed
   - CNCF graduated project with snapshot support

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

**Tasks:**
- Create storage app structure at `kubernetes/apps/kube-system/openebs/`
- Deploy OpenEBS via Flux HelmRelease
- Set openebs-hostpath as default StorageClass
- Verify PVC creation works

### Phase 3: VPN Sidecar Component ✅ COMPLETE

**Goal:** Create reusable Kustomize component for WireGuard VPN sidecars

**Completed:**
- ✅ Created component at `kubernetes/components/vpn-sidecar/`
- ✅ Created deployment patch for wireguard sidecar
- ✅ Configured NET_ADMIN capabilities and sysctls
- ✅ SOPS-encrypted WireGuard NL configuration
- ✅ Local network routing preserved (192.168.x, 10.x, 172.16.x)

### Phase 4: Authentik Authentication ⏳ IN PROGRESS

**Goal:** Deploy Authentik SSO before media apps

**Tasks:**
- Create namespace and app structure
- Deploy Authentik with PostgreSQL + Redis subcharts
- Configure forward auth with Envoy Gateway SecurityPolicy
- Complete initial Authentik setup wizard

### Phase 5: Critical Apps Deployment (NOT STARTED)

**Goal:** Deploy 6 critical apps

**Order:**
1. radarr (no VPN) - validate pattern
2. sonarr (no VPN) - confirm pattern
3. sabnzbd (no VPN) - Usenet client
4. prowlarr (with VPN) - first VPN test
5. qbittorrent (with VPN) - second VPN validation
6. jellyfin (media server) - user-facing

### Phase 6: Monitoring Stack (NOT STARTED - OPTIONAL)

**Goal:** Deploy observability stack

**Tasks:**
- Deploy kube-prometheus-stack
- Configure Grafana with Authentik OAuth
- Add Loki for log aggregation
- Create custom dashboards

### Phase 7: Testing & Validation (NOT STARTED)

**Goal:** Comprehensive testing of all components

## Current Status: Phase 4 In Progress

### What's Working

✅ Talos Linux cluster running (v1.12.1)
✅ Kubernetes running (v1.35.0)
✅ Flux GitOps syncing from GitHub
✅ Cilium CNI operational
✅ Envoy Gateway for ingress
✅ OpenEBS storage provisioner deployed
✅ Talos User Volumes configured
✅ VPN sidecar component ready
✅ Authentik manifests deployed

### Current Task: Provisioning Storage for Authentik

**Task:** Applying Talos User Volume configuration for OpenEBS persistent storage

**Details:**
- User Volume `openebs-system` being provisioned on internal SSD
- WWID-based disk selector ensures correct disk selection
- Will mount at `/var/mnt/openebs-system` with 100GiB minimum
- OpenEBS basePath updated to use User Volume mount point

**What We've Tried:**

1. ✅ Added `wipe: true` patch to force disk wipe
2. ✅ Fixed malformed schematic ID URL (installer vs metal-installer - not the issue)
3. ✅ Verified disk is correctly specified (/dev/sda)
4. ✅ Set up local Docker registry to serve installer image
   - Registry running at 192.168.3.25:5001 (port 5000 blocked by AirPlay)
   - Image: `localhost:5001/installer/039535a70c3bd1667c355eca78571267704e55c8a24785033d183b8f26e39d82:v1.12.1`
5. ✅ Configured registry mirror to redirect factory.talos.dev to local registry
6. ⏳ **CURRENT:** Testing mirror configuration

**Current Configuration (Attempting):**

Mirror config in `talos/patches/global/machine-insecure-registry.yaml`:
```yaml
machine:
  registries:
    mirrors:
      factory.talos.dev:
        endpoints:
          - http://192.168.3.25:5001
```

Image URL in `talconfig.yaml`:
```yaml
talosImageURL: factory.talos.dev/installer/039535a70c3bd1667c355eca78571267704e55c8a24785033d183b8f26e39d82
```

Local registry image path:
```
localhost:5001/installer/039535a70c3bd1667c355eca78571267704e55c8a24785033d183b8f26e39d82:v1.12.1
```

**Errors Observed on Node (via TV screen):**
- `volume status component controller-runtime error evaluating disk no such attribute: system disk` (normal before installation)
- `kubernetes endpoint watch error: ... no route to host` (normal during installation)
- Earlier: `failed to do request: Head <url>: http: server gave HTTP response to HTTPS client`

**Next Steps to Resolve:**

1. Verify local registry has image with correct path structure:
   ```bash
   curl http://localhost:5001/v2/_catalog
   curl http://localhost:5001/v2/installer/039535a70c3bd1667c355eca78571267704e55c8a24785033d183b8f26e39d82/tags/list
   ```

2. If registry structure is correct, regenerate and apply:
   ```bash
   cd talos
   talhelper genconfig
   talosctl apply-config --talosconfig=./clusterconfig/talosconfig --nodes 192.168.3.26 --file=./clusterconfig/kubernetes-homeserver-main.yaml --insecure
   ```

3. If still failing, consider:
   - Try standard Talos installer without factory extensions temporarily
   - Use `talosctl reset` to wipe disk before applying config
   - Check if there's a DNS resolution issue from the node

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

1. **Talos Installation is the blocker** - everything else depends on this working
2. **Local registry is running** at 192.168.3.25:5001 with Talos installer image
3. **Mirror configuration** is the current approach being tested
4. **Node is currently in Windows** - need to boot from USB to maintenance mode
5. **All configs are committed to git** except for Talos secrets (generated during bootstrap)
6. **Fresh start approach** - no data migration, backups restored manually later

## Next Actions (Priority Order)

1. **Fix Talos installation** - This is blocking everything
   - Verify local registry image path structure
   - Test mirror redirection
   - Consider alternative installation methods if mirror fails

2. **Complete Phase 1** - Bootstrap Kubernetes and Flux
   - After Talos installs successfully
   - Run `task bootstrap:apps`
   - Verify all infrastructure pods running

3. **Begin Phase 2** - Deploy OpenEBS storage
   - Create manifests at `kubernetes/apps/kube-system/openebs/`
   - Commit and push to trigger Flux deployment

4. **Continue through phases** 3-7 as outlined above

## Lessons Learned

1. **Port 5000 blocked by AirPlay on macOS** - Use port 5001 for Docker registry
2. **factory.talos.dev can be unreachable** - Local registry mirror is necessary
3. **`wipe: false` by default** - Need explicit `wipe: true` patch for fresh installs
4. **Talos uses HTTPS for registries by default** - Need `http://` prefix in mirror endpoints
5. **VIP configuration is intentional** - 192.168.3.100 for HA even on single node
6. **System disk errors are normal** - Before Talos installation completes

---

**Last Updated:** 2026-01-07
**Current Phase:** Phase 4 (Authentik) - IN PROGRESS
**Next Step:** Apply User Volume config, then verify Authentik PostgreSQL can mount storage
