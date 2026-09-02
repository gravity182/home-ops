# Portwatch

Cloudflare Worker for TCP port monitoring with Telegram notifications.

## Setup

From this directory:

1. Create a KV namespace and add its ID to `wrangler.toml`:
   `wrangler kv namespace create PORTWATCH_KV`
2. Set the required secrets:
   - `wrangler secret put PORTWATCH_TARGET_IP`
   - `wrangler secret put TELEGRAM_BOT_TOKEN`
   - `wrangler secret put TELEGRAM_CHAT_ID`
3. Deploy:
   `wrangler deploy`

## Configuration

Set these non-secret variables in `wrangler.toml`:

- `PORTWATCH_PORTS`: TCP ports to monitor.
- `PORTWATCH_FAILURE_THRESHOLD`: failed probes before an alert.
- `PORTWATCH_REPEAT_INTERVAL_SECONDS`: interval between down alerts.
- `PORTWATCH_CONNECT_TIMEOUT_MS`: TCP connection timeout.
