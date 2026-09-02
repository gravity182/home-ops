type Env = {
  DEADMAN_KV: KVNamespace;
  DEADMAN_AUTH_TOKEN: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  DEADMAN_CHECK_IDS: string;
  DEADMAN_TIMEOUT_SECONDS?: string;
  DEADMAN_REPEAT_INTERVAL_SECONDS?: string;
};

type CheckState = {
  lastPingAt: number;
  down: boolean;
  lastNotificationAt?: number;
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

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseBearerToken(value: string | null): string | null {
  const [scheme, token] = value?.split(" ", 2) ?? [];
  return scheme?.toLowerCase() === "bearer" && token?.trim() ? token.trim() : null;
}

function checkIds(env: Env): string[] {
  return env.DEADMAN_CHECK_IDS.split(",")
    .map((checkId) => checkId.trim())
    .filter(Boolean);
}

function stateKey(checkId: string): string {
  return `deadman:${checkId}`;
}

async function loadState(env: Env, checkId: string): Promise<CheckState | null> {
  const value = await env.DEADMAN_KV.get(stateKey(checkId));
  if (!value) return null;

  try {
    const parsed = JSON.parse(value) as Partial<CheckState>;
    if (
      typeof parsed.lastPingAt === "number" &&
      Number.isInteger(parsed.lastPingAt) &&
      typeof parsed.down === "boolean" &&
      (parsed.lastNotificationAt === undefined ||
        (typeof parsed.lastNotificationAt === "number" &&
          Number.isInteger(parsed.lastNotificationAt)))
    ) {
      return parsed as CheckState;
    }
  } catch {
    // Treat invalid state as a check that has not yet received a heartbeat.
  }

  return null;
}

async function saveState(env: Env, checkId: string, state: CheckState): Promise<void> {
  await env.DEADMAN_KV.put(stateKey(checkId), JSON.stringify(state));
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

function downMessage(checkId: string): string {
  return `\u{1F525} DEADMAN DOWN: ${checkId}`;
}

function recoveredMessage(checkId: string): string {
  return `\u{2705} DEADMAN RECOVERED: ${checkId}`;
}

async function handlePing(request: Request, env: Env, checkId: string): Promise<Response> {
  if (parseBearerToken(request.headers.get("authorization")) !== env.DEADMAN_AUTH_TOKEN) {
    return jsonResponse(401, { ok: false, error: "unauthorized" });
  }

  const now = nowSeconds();
  const state = await loadState(env, checkId);
  await saveState(env, checkId, {
    lastPingAt: now,
    down: state?.down ?? false,
    lastNotificationAt: state?.lastNotificationAt,
  });

  return jsonResponse(200, { ok: true, checkId, lastPingAt: now });
}

async function evaluateCheck(
  env: Env,
  checkId: string,
  timeoutSeconds: number,
  repeatIntervalSeconds: number,
): Promise<void> {
  const state = await loadState(env, checkId);
  if (!state) return;

  const now = nowSeconds();
  if (now - state.lastPingAt <= timeoutSeconds) {
    if (state.down) {
      await sendTelegram(env, recoveredMessage(checkId));
      await saveState(env, checkId, { lastPingAt: state.lastPingAt, down: false });
    }
    return;
  }

  if (
    !state.down ||
    now - (state.lastNotificationAt ?? 0) >= repeatIntervalSeconds
  ) {
    await sendTelegram(env, downMessage(checkId));
    await saveState(env, checkId, {
      ...state,
      down: true,
      lastNotificationAt: now,
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const segments = url.pathname.split("/").filter(Boolean);

    if (request.method === "POST" && segments.length === 2 && segments[0] === "ping") {
      return handlePing(request, env, segments[1]);
    }

    if (request.method === "GET" && url.pathname === "/healthz") {
      return jsonResponse(200, { ok: true });
    }

    return jsonResponse(404, { ok: false, error: "not found" });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const timeoutSeconds = parsePositiveInteger(env.DEADMAN_TIMEOUT_SECONDS, 600);
    const repeatIntervalSeconds = parsePositiveInteger(
      env.DEADMAN_REPEAT_INTERVAL_SECONDS,
      3600,
    );

    await Promise.all(
      checkIds(env).map((checkId) =>
        evaluateCheck(env, checkId, timeoutSeconds, repeatIntervalSeconds),
      ),
    );
  },
};
