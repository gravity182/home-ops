import { connect } from "cloudflare:sockets";

type Env = {
  PORTWATCH_KV: KVNamespace;
  PORTWATCH_PORTS: string;
  PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD: string;
  PORTWATCH_REMINDER_SECONDS: string;
  PORTWATCH_CONNECT_TIMEOUT_MS: string;

  // Secrets (set via `wrangler secret put ...`)
  PORTWATCH_TARGET_IP: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
};

type PortState = {
  status: "up" | "down";
  consecutiveFailures: number;
  firstFailureAt?: number;
  downAt?: number;
  lastReminderAt?: number;
};

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function parseIntStrict(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return parsed;
}

function parsePorts(ports: string): number[] {
  return ports
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => Number.parseInt(p, 10))
    .filter((p) => Number.isFinite(p) && p > 0 && p <= 65535);
}

function portKey(targetIp: string, port: number): string {
  return `portwatch:state:${targetIp}:${port}`;
}

async function loadState(env: Env, key: string): Promise<PortState> {
  const raw = await env.PORTWATCH_KV.get(key);
  if (!raw) {
    return { status: "up", consecutiveFailures: 0 };
  }
  try {
    return JSON.parse(raw) as PortState;
  } catch {
    return { status: "up", consecutiveFailures: 0 };
  }
}

async function saveState(env: Env, key: string, state: PortState): Promise<void> {
  await env.PORTWATCH_KV.put(key, JSON.stringify(state));
}

async function sendTelegram(env: Env, text: string): Promise<void> {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const payload = {
    chat_id: env.TELEGRAM_CHAT_ID,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };

  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Telegram sendMessage failed: ${response.status} ${body}`);
  }
}

async function tcpProbe(hostname: string, port: number, timeoutMs: number): Promise<boolean> {
  let socket:
    | ReturnType<typeof connect>
    | undefined;
  try {
    socket = connect({ hostname, port });
    await Promise.race([
      socket.opened,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("tcp probe timeout")), timeoutMs),
      ),
    ]);
    return true;
  } catch {
    return false;
  } finally {
    try {
      socket?.close();
    } catch {
      // ignore
    }
  }
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function evaluatePort(env: Env, targetIp: string, port: number): Promise<void> {
  const connectTimeoutMs = parseIntStrict(env.PORTWATCH_CONNECT_TIMEOUT_MS, 3000);
  const threshold = parseIntStrict(env.PORTWATCH_CONSECUTIVE_FAILURES_THRESHOLD, 3);
  const reminderSeconds = parseIntStrict(env.PORTWATCH_REMINDER_SECONDS, 21600);
  const now = nowSeconds();

  const key = portKey(targetIp, port);
  const state = await loadState(env, key);

  const isOpen = await tcpProbe(targetIp, port, connectTimeoutMs);

  if (isOpen) {
    if (state.status === "down") {
      await sendTelegram(
        env,
        `✅ <b>PORT RECOVERED</b>: <code>${escapeHtml(targetIp)}:${port}</code>`,
      );
      await saveState(env, key, { status: "up", consecutiveFailures: 0 });
      return;
    }

    if (state.consecutiveFailures !== 0) {
      await saveState(env, key, { ...state, consecutiveFailures: 0, firstFailureAt: undefined });
    }
    return;
  }

  // Failed probe
  if (state.status === "down") {
    const lastReminderAt = state.lastReminderAt ?? state.downAt ?? now;
    if (reminderSeconds > 0 && now - lastReminderAt >= reminderSeconds) {
      await sendTelegram(
        env,
        `🔥 <b>PORT STILL DOWN</b>: <code>${escapeHtml(targetIp)}:${port}</code>`,
      );
      await saveState(env, key, { ...state, lastReminderAt: now });
    }
    return;
  }

  const nextFailures = (state.consecutiveFailures ?? 0) + 1;
  const nextFirstFailureAt = state.firstFailureAt ?? now;

  if (nextFailures < threshold) {
    // Only write during the initial streak buildup. This caps writes during short blips to < threshold per event.
    await saveState(env, key, {
      ...state,
      consecutiveFailures: nextFailures,
      firstFailureAt: nextFirstFailureAt,
    });
    return;
  }

  // Transition to DOWN (single alert), then reminders handled above.
  await sendTelegram(
    env,
    `🔥 <b>PORT DOWN</b>: <code>${escapeHtml(targetIp)}:${port}</code>`,
  );
  await saveState(env, key, {
    status: "down",
    consecutiveFailures: nextFailures,
    firstFailureAt: nextFirstFailureAt,
    downAt: now,
    lastReminderAt: now,
  });
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }
    return new Response("not found", { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const ports = parsePorts(env.PORTWATCH_PORTS);
    if (!env.PORTWATCH_TARGET_IP || ports.length === 0) return;

    const targetIp = env.PORTWATCH_TARGET_IP.trim();
    await Promise.all(ports.map((port) => evaluatePort(env, targetIp, port)));
  },
};
