#!/usr/bin/env bash
set -euo pipefail

node_ip="${1:-}"

cache_dir="../.private/talos-image-cache"
mirror_address="192.168.3.25:5001"

if [[ -z "${node_ip}" ]]; then
  echo "usage: $0 <node-ip>" >&2
  exit 2
fi

talos_image="$(yq -r ".nodes[] | select(.ipAddress == \"${node_ip}\") | .talosImageURL" talconfig.yaml)"
talos_version="$(yq -r ".talosVersion" talenv.yaml)"

if [[ -z "${talos_image}" || "${talos_image}" == "null" ]]; then
  echo "No Talos image found for node IP ${node_ip}" >&2
  exit 1
fi

if [[ -z "${talos_version}" || "${talos_version}" == "null" ]]; then
  echo "No talosVersion found in talenv.yaml" >&2
  exit 1
fi

source_image="${talos_image}:${talos_version}"

echo "Source:      ${source_image}"
echo "Cache:       ${cache_dir}"
echo "Mirror:      http://${mirror_address}"
echo "Platform:    linux/amd64"

mkdir -p "${cache_dir}"

talosctl image cache-create \
  --force \
  --layout flat \
  --platform linux/amd64 \
  --image-cache-path "${cache_dir}" \
  --images "${source_image}"

talosctl image cache-serve \
  --address "${mirror_address}" \
  --image-cache-path "${cache_dir}" \
  --mirror factory.talos.dev
