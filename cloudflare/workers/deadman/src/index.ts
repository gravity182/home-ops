type Env = {
  DEADMAN_KV: KVNamespace;
  DEADMAN_AUTH_TOKEN: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  DEADMAN_CHECK_IDS: string;
  DEADMAN_TIMEOUT_SECONDS?: string;
  DEADMAN_DEDUPE_SECONDS?: string;
};

type CheckState = {
  lastPingAt: number;
  status: "up" | "down";
  lastDownNotifiedAt?: number;
  lastUpNotifiedAt?: number;
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function parseBearerToken(authHeader: string | null): string | null {
  if (!authHeader) return null;
  const [scheme, token] = authHeader.split(" ", 2);
  if (scheme?.toLowerCase() !== "bearer") return null;
  return token?.trim() || null;
}

function getTimeoutSeconds(env: Env): number {
  const parsed = Number(env.DEADMAN_TIMEOUT_SECONDS ?? "600");
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 600;
}

function getDedupeSeconds(env: Env): number {
  const parsed = Number(env.DEADMAN_DEDUPE_SECONDS ?? "3600");
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 3600;
}

function getCheckIds(env: Env): string[] {
  return (env.DEADMAN_CHECK_IDS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function stateKey(checkId: string): string {
  return `deadman:check:${checkId}`;
}

function formatDurationCompact(secondsTotal: number): string {
  const seconds = Math.max(0, Math.floor(secondsTotal));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (days > 0) return `${days}d${hours}h`;
  if (hours > 0) return `${hours}h${minutes}m`;
  if (minutes > 0) return `${minutes}m${secs}s`;
  return `${secs}s`;
}

async function loadState(env: Env, checkId: string): Promise<CheckState | null> {
  const raw = await env.DEADMAN_KV.get(stateKey(checkId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CheckState;
  } catch {
    return null;
  }
}

async function saveState(env: Env, checkId: string, state: CheckState): Promise<void> {
  await env.DEADMAN_KV.put(stateKey(checkId), JSON.stringify(state));
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

async function handlePing(request: Request, env: Env, checkId: string): Promise<Response> {
  const presentedToken = parseBearerToken(request.headers.get("authorization"));
  if (!presentedToken || presentedToken !== env.DEADMAN_AUTH_TOKEN) {
    return jsonResponse(401, { ok: false, error: "unauthorized" });
  }

  const now = nowSeconds();
  const existing = await loadState(env, checkId);

  const next: CheckState = existing
    ? { ...existing, lastPingAt: now }
    : { lastPingAt: now, status: "up" };

  await saveState(env, checkId, next);
  return jsonResponse(200, { ok: true, checkId, lastPingAt: now });
}

async function evaluateChecks(env: Env): Promise<void> {
  const checkIds = getCheckIds(env);
  const timeoutSeconds = getTimeoutSeconds(env);
  const dedupeSeconds = getDedupeSeconds(env);
  const now = nowSeconds();

  for (const checkId of checkIds) {
    const state = await loadState(env, checkId);
    if (!state) {
      continue; // do not alert until the first ping is received
    }

    const age = now - state.lastPingAt;
    const isDown = age > timeoutSeconds;

    if (isDown) {
      const shouldNotify =
        state.status !== "down" ||
        !state.lastDownNotifiedAt ||
        now - state.lastDownNotifiedAt >= dedupeSeconds;

      if (!shouldNotify) {
        continue;
      }

      await sendTelegram(
        env,
        `🔥 <b>DEADMAN DOWN</b>: <code>${checkId}</code>\nLast ping: <code>${formatDurationCompact(age)}</code> ago`,
      );

      await saveState(env, checkId, {
        ...state,
        status: "down",
        lastDownNotifiedAt: now,
      });

      continue;
    }

    if (state.status === "down") {
      await sendTelegram(env, `✅ <b>DEADMAN RECOVERED</b>: <code>${checkId}</code>`);
      await saveState(env, checkId, {
        ...state,
        status: "up",
        lastUpNotifiedAt: now,
      });
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const segments = url.pathname.split("/").filter(Boolean);

    if (request.method === "POST" && segments.length === 2 && segments[0] === "ping") {
      const checkId = segments[1];
      return handlePing(request, env, checkId);
    }

    if (request.method === "GET" && url.pathname === "/healthz") {
      return jsonResponse(200, { ok: true });
    }

    return jsonResponse(404, { ok: false, error: "not found" });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await evaluateChecks(env);
  },
};
