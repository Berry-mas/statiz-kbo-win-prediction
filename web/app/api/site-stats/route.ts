import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const KEY_PREFIX = "y-wins:site-stats";
const SITE_SCOPE = "site";

type SiteStatsBody = {
  action?: unknown;
  visitorId?: unknown;
  scope?: unknown;
};

type RedisJson<T> = {
  result?: T;
  error?: string;
};

export async function POST(request: NextRequest) {
  const config = getRedisConfig();
  if (!config) {
    return NextResponse.json({ configured: false, views: 0, likes: 0, liked: false }, { status: 503 });
  }

  const body = await parseJson(request);
  const action = body.action === "view" || body.action === "like" ? body.action : null;
  const visitorId = normalizeVisitorId(body.visitorId);
  const scope = normalizeScope(body.scope);

  if (!action) {
    return NextResponse.json({ error: "invalid_action" }, { status: 400 });
  }
  if (!visitorId) {
    return NextResponse.json({ error: "invalid_visitor" }, { status: 400 });
  }

  const keys = statKeys(scope);

  try {
    if (action === "view") {
      await redisCommand<number>(config, ["INCR", keys.views]);
    }

    let liked = await redisCommand<number>(config, ["SISMEMBER", keys.likedVisitors, visitorId]);
    if (action === "like" && liked !== 1) {
      const added = await redisCommand<number>(config, ["SADD", keys.likedVisitors, visitorId]);
      if (added === 1) {
        await redisCommand<number>(config, ["INCR", keys.likes]);
      }
      liked = 1;
    }

    const [views, likes] = await Promise.all([
      redisCommand<string | number | null>(config, ["GET", keys.views]),
      redisCommand<string | number | null>(config, ["GET", keys.likes]),
    ]);

    return NextResponse.json(
      {
        configured: true,
        views: toCount(views),
        likes: toCount(likes),
        liked: liked === 1,
      },
      {
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "redis_error";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

function getRedisConfig(): { url: string; token: string } | null {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) {
    return null;
  }
  return { url: url.replace(/\/$/, ""), token };
}

async function redisCommand<T>(
  config: { url: string; token: string },
  command: [string, ...string[]],
): Promise<T> {
  const response = await fetch(`${config.url}/${command.map(encodeURIComponent).join("/")}`, {
    headers: {
      Authorization: `Bearer ${config.token}`,
    },
    cache: "no-store",
  });
  const payload = (await response.json()) as RedisJson<T>;

  if (!response.ok || payload.error) {
    throw new Error(payload.error ?? `redis_http_${response.status}`);
  }

  return payload.result as T;
}

async function parseJson(request: NextRequest): Promise<SiteStatsBody> {
  try {
    return (await request.json()) as SiteStatsBody;
  } catch {
    return {};
  }
}

function normalizeVisitorId(value: unknown): string | null {
  if (typeof value !== "string" || !/^[a-f0-9-]{20,80}$/i.test(value)) {
    return null;
  }
  return value;
}

function normalizeScope(value: unknown): string {
  if (typeof value !== "string" || !/^[a-z0-9:-]{1,80}$/i.test(value)) {
    return SITE_SCOPE;
  }
  return value;
}

function statKeys(scope: string) {
  return {
    views: `${KEY_PREFIX}:${scope}:views`,
    likes: `${KEY_PREFIX}:${scope}:likes`,
    likedVisitors: `${KEY_PREFIX}:${scope}:liked-visitors`,
  };
}

function toCount(value: string | number | null): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}
