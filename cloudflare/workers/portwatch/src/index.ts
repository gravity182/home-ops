import { connect } from "cloudflare:sockets";

type Env = {
  PORTWATCH_KV: KVNamespace;
  PORTWATCH_PORTS: string;
  PORTWATCH_FAILURE_THRESHOLD: string;
  PORTWATCH_REPEAT_INTERVAL_SECONDS: string;
  PORTWATCH_CONNECT_TIMEOUT_MS: string;
  PORTWATCH_TARGET_IP: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
};

type PortState = {
  failures: number;
  down: boolean;
  lastNotificationAt?: number;
};

function parsePositiveInteger(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parsePorts(value: string): number[] {
  return value
    .split(",")
    .map((port) => Number(port.trim()))
    .filter((port) => Number.isInteger(port) && port > 0 && port <= 65535);
}

function portKey(targetIp: string, port: number): string {
  return `portwatch:${targetIp}:${port}`;
}

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

async function loadState(env: Env, key: string): Promise<PortState> {
  const value = await env.PORTWATCH_KV.get(key);
  if (!value) return { failures: 0, down: false };

  try {
    const parsed = JSON.parse(value) as Partial<PortState>;
    if (
      typeof parsed.failures === "number" &&
      Number.isInteger(parsed.failures) &&
      parsed.failures >= 0 &&
      typeof parsed.down === "boolean" &&
      (parsed.lastNotificationAt === undefined ||
        (typeof parsed.lastNotificationAt === "number" &&
          Number.isInteger(parsed.lastNotificationAt)))
    ) {
      return parsed as PortState;
    }
  } catch {
    // Treat invalid state as a new incident.
  }

  return { failures: 0, down: false };
}

async function sendTelegram(env: Env, text: string): Promise<void> {
  const response = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: env.TELEGRAM_CHAT_ID,
        text,
        disable_web_page_preview: true,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(`Telegram sendMessage failed with ${response.status}`);
  }
}

async function tcpProbe(hostname: string, port: number, timeoutMs: number): Promise<boolean> {
  let socket: ReturnType<typeof connect> | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;

  try {
    socket = connect({ hostname, port });
    await Promise.race([
      socket.opened,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error("TCP probe timed out")), timeoutMs);
      }),
    ]);
    return true;
  } catch {
    return false;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    await socket?.close().catch(() => undefined);
  }
}

function downMessage(targetIp: string, port: number): string {
  return `\u{1F525} PORT DOWN: ${targetIp}:${port}`;
}

function recoveredMessage(targetIp: string, port: number): string {
  return `\u{2705} PORT RECOVERED: ${targetIp}:${port}`;
}

async function evaluatePort(env: Env, targetIp: string, port: number): Promise<void> {
  const threshold = parsePositiveInteger(env.PORTWATCH_FAILURE_THRESHOLD, 3);
  const repeatIntervalSeconds = parsePositiveInteger(
    env.PORTWATCH_REPEAT_INTERVAL_SECONDS,
    43200,
  );
  const timeoutMs = parsePositiveInteger(env.PORTWATCH_CONNECT_TIMEOUT_MS, 5000);
  const key = portKey(targetIp, port);
  const state = await loadState(env, key);

  if (await tcpProbe(targetIp, port, timeoutMs)) {
    if (state.down) {
      await sendTelegram(env, recoveredMessage(targetIp, port));
    }
    if (state.down || state.failures > 0) {
      await env.PORTWATCH_KV.delete(key);
    }
    return;
  }

  const now = nowSeconds();
  if (state.down) {
    if (now - (state.lastNotificationAt ?? 0) >= repeatIntervalSeconds) {
      await sendTelegram(env, downMessage(targetIp, port));
      await env.PORTWATCH_KV.put(
        key,
        JSON.stringify({ ...state, lastNotificationAt: now }),
      );
    }
    return;
  }

  const failures = state.failures + 1;
  if (failures < threshold) {
    await env.PORTWATCH_KV.put(key, JSON.stringify({ failures, down: false }));
    return;
  }

  await sendTelegram(env, downMessage(targetIp, port));
  await env.PORTWATCH_KV.put(
    key,
    JSON.stringify({ failures, down: true, lastNotificationAt: now }),
  );
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {
      return new Response("ok");
    }
    return new Response("not found", { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const targetIp = env.PORTWATCH_TARGET_IP?.trim();
    const ports = parsePorts(env.PORTWATCH_PORTS);
    if (!targetIp || ports.length === 0) return;

    await Promise.all(ports.map((port) => evaluatePort(env, targetIp, port)));
  },
};
