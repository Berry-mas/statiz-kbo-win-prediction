"use client";

import { useEffect, useRef, useState } from "react";

type SiteStats = {
  views: number;
  likes: number;
  liked: boolean;
  configured: boolean;
};

const VISITOR_ID_KEY = "y-wins-visitor-id";
const INITIAL_STATS: SiteStats = {
  views: 0,
  likes: 0,
  liked: false,
  configured: true,
};

export function SiteStatsStrip() {
  const [stats, setStats] = useState<SiteStats>(INITIAL_STATS);
  const [status, setStatus] = useState<"loading" | "ready" | "pending" | "offline">("loading");
  const countedRef = useRef(false);

  useEffect(() => {
    if (countedRef.current) {
      return;
    }
    countedRef.current = true;

    const visitorId = getVisitorId();
    void updateStats("view", visitorId);
  }, []);

  async function updateStats(action: "view" | "like", visitorId: string) {
    setStatus(action === "like" ? "pending" : "loading");
    try {
      const response = await fetch("/api/site-stats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, visitorId }),
      });
      const payload = (await response.json()) as Partial<SiteStats>;

      if (!response.ok || payload.configured === false) {
        setStats((current) => ({ ...current, configured: false }));
        setStatus("offline");
        return;
      }

      setStats({
        views: safeCount(payload.views),
        likes: safeCount(payload.likes),
        liked: payload.liked === true,
        configured: true,
      });
      setStatus("ready");
    } catch {
      setStatus("offline");
    }
  }

  const disabled = status === "loading" || status === "pending" || stats.liked || !stats.configured;

  return (
    <section className="site-stats-strip" aria-label="Site activity">
      <div className="site-stat">
        <span data-en="Views" data-ko="조회">Views</span>
        <strong>{formatCount(stats.views)}</strong>
      </div>
      <div className="site-stat">
        <span data-en="Likes" data-ko="좋아요">Likes</span>
        <strong>{formatCount(stats.likes)}</strong>
      </div>
      <button
        aria-pressed={stats.liked}
        className="site-like-button"
        disabled={disabled}
        onClick={() => updateStats("like", getVisitorId())}
        type="button"
      >
        <span className="baseball-mark" aria-hidden="true">
          ⚾️
        </span>
        <span
          data-en={stats.liked ? "Liked" : status === "pending" ? "Saving" : "Like"}
          data-ko={stats.liked ? "좋아요 완료" : status === "pending" ? "저장 중" : "좋아요"}
        >
          {stats.liked ? "Liked" : status === "pending" ? "Saving" : "Like"}
        </span>
      </button>
      {status === "offline" ? (
        <span className="site-stats-note" data-en="Stats offline" data-ko="통계 연결 안 됨">
          Stats offline
        </span>
      ) : null}
    </section>
  );
}

function getVisitorId(): string {
  const stored = window.localStorage.getItem(VISITOR_ID_KEY);
  if (stored && /^[a-f0-9-]{20,80}$/i.test(stored)) {
    return stored;
  }

  const cookieValue = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${VISITOR_ID_KEY}=`))
    ?.split("=")[1];
  if (cookieValue && /^[a-f0-9-]{20,80}$/i.test(cookieValue)) {
    window.localStorage.setItem(VISITOR_ID_KEY, cookieValue);
    return cookieValue;
  }

  const generated = window.crypto.randomUUID();
  window.localStorage.setItem(VISITOR_ID_KEY, generated);
  document.cookie = `${VISITOR_ID_KEY}=${generated}; Max-Age=31536000; Path=/; SameSite=Lax`;
  return generated;
}

function safeCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
