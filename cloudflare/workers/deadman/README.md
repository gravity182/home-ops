# Deadman switch (Cloudflare Worker)

External heartbeat monitor for Alertmanager / Prometheus `Watchdog`, implemented as a Cloudflare Worker.

## Behavior

- Alertmanager sends a webhook heartbeat to the Worker on the `Watchdog` route `repeat_interval` (10m in this repo).
- The Worker stores `lastPingAt` in Workers KV keyed by `checkId`.
- A cron trigger runs every minute and evaluates staleness:
  - If `now - lastPingAt > DEADMAN_TIMEOUT_SECONDS`: emit `DEADMAN DOWN`
  - If a previously down check receives fresh pings again: emit `DEADMAN RECOVERED`
- While down, alerts are rate-limited by `DEADMAN_DEDUPE_SECONDS` (default 1h).

## Endpoints

- `POST /ping/:checkId`
  - Requires `Authorization: Bearer <token>`
  - Body is ignored (Alertmanager webhook JSON is accepted)

## Configuration (Cloudflare)

Create a KV namespace and bind it as `DEADMAN_KV`, then set the following secrets/vars:

- Secret: `DEADMAN_AUTH_TOKEN` (same token as in `alertmanager-deadman-secret`)
- Secret: `TELEGRAM_BOT_TOKEN` (reuse your existing Alertmanager bot token)
- Secret: `TELEGRAM_CHAT_ID` (same chat id as your alerts)
- Var: `DEADMAN_CHECK_IDS` (comma-separated, e.g. `watchdog-homelab,backup-nas`)
- Optional var: `DEADMAN_TIMEOUT_SECONDS` (default `720`)
- Optional var: `DEADMAN_DEDUPE_SECONDS` (default `3600`)

## Deploy

From this directory:

1) Create KV namespace:
   - `wrangler kv namespace create DEADMAN_KV`
2) Put the KV id into `wrangler.toml` under `[[kv_namespaces]]`
3) Set secrets:
   - `wrangler secret put DEADMAN_AUTH_TOKEN`
   - `wrangler secret put TELEGRAM_BOT_TOKEN`
   - `wrangler secret put TELEGRAM_CHAT_ID`
4) Deploy:
   - `wrangler deploy`

After deploy, update the Alertmanager webhook URL in:

- `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`

Set `SECRET_DEADMAN_WORKER_URL` (base URL, without `/ping/...`) in your cluster secrets (SOPS-encrypted), then Flux substitution will wire it into Alertmanager.

`workers.dev` URL format: `<WORKER_NAME>.<YOUR_SUBDOMAIN>.workers.dev`

## Resource usage estimate (Workers + KV)

Parameters:
- `checks`: `len(DEADMAN_CHECK_IDS)`
- cron: 60s
- heartbeat interval: configured in Alertmanager (10m in this repo)

Workers requests/day (cron):
- `86400 / 60` = **1,440**

Workers requests/day (heartbeats):
- `checks * (86400 / heartbeat_interval_seconds)`
- at 10m: `checks * 144`

KV reads/day (cron evaluation):
- `checks * 1,440`

KV writes/day (heartbeats):
- roughly `checks * 144` at 10m (plus occasional state-change writes for DOWN/RECOVERED)

Reference limits (KV Free tier):
- reads/day: **100,000**
- writes/day: **1,000**

## Notes

- The Worker does not emit DOWN/RECOVERED until it has received at least one ping per `checkId`.
