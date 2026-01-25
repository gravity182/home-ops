# Portwatch (Cloudflare Worker)

Active TCP port reachability checks from Cloudflare to your public IP.

## What it does

- Runs every minute via cron trigger.
- Attempts a TCP connect to configured ports on your public IP.
- Alerts to Telegram:
  - `PORT DOWN` only after `PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD` consecutive failures.
  - `PORT STILL DOWN` reminders every `PORTWATCH_REMINDER_SECONDS` (default 6h).
  - `PORT RECOVERED` when connectivity returns.

This Worker is intentionally separate from the Alertmanager deadman Worker:
- `deadman-switch`: liveness of the alerting pipeline via heartbeats.
- `portwatch`: reachability of inbound TCP ports via active probes.

## Configuration

### Required secrets (per Worker)

Set via Wrangler (v4 syntax):

- `PORTWATCH_TARGET_IP`: your public IP (the Worker probes this; do not commit it to git).
- `TELEGRAM_BOT_TOKEN`: bot token (you can reuse the same bot as Alertmanager/deadman).
- `TELEGRAM_CHAT_ID`: destination chat id.

### Non-secret vars

Defined in `wrangler.toml`:

- `PORTWATCH_PORTS`: comma-separated ports (default `443,30413`)
- `PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD`: default `3`
- `PORTWATCH_CONNECT_TIMEOUT_MS`: default `3000`
- `PORTWATCH_REMINDER_SECONDS`: default `21600` (6h)

## Deploy

From `cloudflare/workers/portwatch`:

1) Login:
   - `wrangler login`
2) Create KV namespace:
   - `wrangler kv namespace create PORTWATCH_KV`
   - Paste the namespace id into `wrangler.toml` under `[[kv_namespaces]]`.
3) Set secrets:
   - `wrangler secret put PORTWATCH_TARGET_IP`
   - `wrangler secret put TELEGRAM_BOT_TOKEN`
   - `wrangler secret put TELEGRAM_CHAT_ID`
4) Deploy:
   - `wrangler deploy`

## Resource usage estimate (Workers + KV)

Parameters (defaults in `wrangler.toml`):
- `ports`: 2
- `interval`: 60s (cron `* * * * *`)
- `PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD`: 3
- `PORTWATCH_REMINDER_SECONDS`: 21600 (6h)

Workers requests/day:
- `86400 / interval` = `86400 / 60` = **1,440**

KV reads/day:
- `ports * (86400 / interval)` = `2 * 1,440` = **2,880**

KV writes:
- Steady-state healthy: **0**
- Single sustained outage (first day, per port):
  - streak buildup: up to `PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD` writes (default 3)
  - transition to DOWN: 1 write
  - reminders: `86400 / PORTWATCH_REMINDER_SECONDS` = `86400 / 21600` = 4 writes/day
  - recovery: 1 write
  - total (default): `3 + 1 + 4 + 1` = **9 writes/port/day**
- For 2 ports: **~18 writes/day** during a sustained outage, otherwise near-zero.

Reference limits (KV Free tier):
- reads/day: **100,000**
- writes/day: **1,000**

The implementation avoids writing on every cron tick while a port remains down; it only writes on state changes and reminder intervals.
