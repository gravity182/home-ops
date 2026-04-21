# Home Ops

Welcome to my home-ops repo!

## ✨ Features

A Kubernetes cluster deployed with [Talos Linux](https://github.com/siderolabs/talos) and [Flux](https://github.com/fluxcd/flux2) using [GitHub](https://github.com/) as the Git provider, [sops](https://github.com/getsops/sops) to manage secrets.

Other components worth mentioning:
- [cilium](https://github.com/cilium/cilium)
- [cert-manager](https://github.com/cert-manager/cert-manager)
- [reloader](https://github.com/stakater/Reloader)
- [envoy-gateway](https://github.com/envoyproxy/gateway)
- [external-dns](https://github.com/kubernetes-sigs/external-dns)
- [Intel GPU resource drivers for Kubernetes](https://github.com/intel/intel-resource-drivers-for-kubernetes)

**Other features include:**

- Workflow automation w/ [GitHub Actions](https://github.com/features/actions)
- Dependency automation w/ [Renovate](https://www.mend.io/renovate)

## Development

Enable the local Conventional Commits check:

```bash
mise install
mise exec -- pre-commit install -t commit-msg
```

If this clone previously installed the hook with a global `pre-commit`, run the install command again after switching to `mise`. The generated Git hook embeds the interpreter path used at install time.
