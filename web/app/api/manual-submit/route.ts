import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_REPOSITORY = "Berry-mas/statiz-kbo-win-prediction";
const DEFAULT_WORKFLOW_ID = "manual-submit.yml";
const DEFAULT_REF = "main";

type ManualSubmitBody = {
  date?: unknown;
};

export async function POST(request: NextRequest) {
  const manualToken = process.env.MANUAL_SUBMIT_TOKEN;
  const githubToken = process.env.GITHUB_ACTIONS_TRIGGER_TOKEN;

  if (!manualToken || !githubToken) {
    return NextResponse.json(
      { ok: false, error: "manual_submit_not_configured" },
      { status: 503 },
    );
  }

  const providedToken = request.headers.get("x-manual-submit-token") ?? "";
  if (!sameToken(providedToken, manualToken)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const body = await parseJson(request);
  const date = normalizeDate(body.date);
  if (date === null) {
    return NextResponse.json({ ok: false, error: "invalid_date" }, { status: 400 });
  }

  const repository = process.env.GITHUB_REPOSITORY_SLUG ?? DEFAULT_REPOSITORY;
  const workflowId = process.env.GITHUB_WORKFLOW_ID ?? DEFAULT_WORKFLOW_ID;
  const ref = process.env.GITHUB_WORKFLOW_REF ?? DEFAULT_REF;
  const response = await fetch(
    `https://api.github.com/repos/${repository}/actions/workflows/${workflowId}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${githubToken}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref,
        inputs: {
          date,
        },
      }),
    },
  );

  if (!response.ok) {
    const detail = await response.text();
    return NextResponse.json(
      { ok: false, error: "github_dispatch_failed", status: response.status, detail },
      { status: 502 },
    );
  }

  return NextResponse.json({ ok: true, workflow: workflowId, ref, date });
}

async function parseJson(request: NextRequest): Promise<ManualSubmitBody> {
  try {
    return (await request.json()) as ManualSubmitBody;
  } catch {
    return {};
  }
}

function normalizeDate(value: unknown): string | null {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  return value;
}

function sameToken(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return timingSafeEqual(leftBuffer, rightBuffer);
}
