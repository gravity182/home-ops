# Deadman Switch

Cloudflare Worker for heartbeat monitoring with Telegram notifications.

## Endpoint

`POST /ping/:checkId` requires `Authorization: Bearer <token>`.

## Setup

From this directory:

1. Create a KV namespace and add its ID to `wrangler.toml`:
   `wrangler kv namespace create DEADMAN_KV`
2. Set the required secrets:
   - `wrangler secret put DEADMAN_AUTH_TOKEN`
   - `wrangler secret put TELEGRAM_BOT_TOKEN`
   - `wrangler secret put TELEGRAM_CHAT_ID`
3. Deploy:
   `wrangler deploy`

## Configuration

Set these non-secret variables in `wrangler.toml`:

- `DEADMAN_CHECK_IDS`: heartbeat check IDs.
- `DEADMAN_TIMEOUT_SECONDS`: heartbeat timeout.
- `DEADMAN_REPEAT_INTERVAL_SECONDS`: interval between down alerts.
