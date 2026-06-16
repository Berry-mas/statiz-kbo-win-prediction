"use client";

import { FormEvent, useState } from "react";

type SubmitState =
  | { status: "idle"; message: string }
  | { status: "pending"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

export function ManualSubmitPanel() {
  const [token, setToken] = useState("");
  const [date, setDate] = useState("");
  const [state, setState] = useState<SubmitState>({
    status: "idle",
    message: "Ready",
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ status: "pending", message: "Dispatching" });

    try {
      const response = await fetch("/api/manual-submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-manual-submit-token": token,
        },
        body: JSON.stringify({ date }),
      });
      const payload = (await response.json()) as { ok?: boolean; error?: string };

      if (!response.ok || !payload.ok) {
        setState({
          status: "error",
          message: payload.error ?? `HTTP ${response.status}`,
        });
        return;
      }

      setState({ status: "success", message: "Queued on submit server" });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "Request failed",
      });
    }
  }

  return (
    <form className="manual-submit" onSubmit={submit}>
      <div className="manual-submit-heading">
        <span className={`status-dot status-${state.status}`} aria-label={state.status} />
      </div>
      <label>
        <span data-en="Password" data-ko="비밀번호">Password</span>
        <input
          autoComplete="current-password"
          onChange={(event) => setToken(event.target.value)}
          placeholder="admin password"
          type="password"
          value={token}
        />
      </label>
      <label>
        <span data-en="Date" data-ko="날짜">Date</span>
        <input
          onChange={(event) => setDate(event.target.value)}
          pattern="\d{4}-\d{2}-\d{2}"
          placeholder="YYYY-MM-DD"
          type="text"
          value={date}
        />
      </label>
      <button
        data-en={state.status === "pending" ? "Submitting" : "Submit Now"}
        data-ko={state.status === "pending" ? "제출 중" : "지금 제출"}
        disabled={state.status === "pending" || token.length === 0}
        type="submit"
      >
        {state.status === "pending" ? "Submitting" : "Submit Now"}
      </button>
      <p
        className={`manual-submit-state state-${state.status}`}
        data-en={state.message}
        data-ko={translateSubmitMessage(state.message)}
      >
        {state.message}
      </p>
    </form>
  );
}

function translateSubmitMessage(message: string): string {
  const labels: Record<string, string> = {
    Dispatching: "제출 요청 중",
    "Queued on submit server": "제출 서버에 예약됨",
    Ready: "준비 완료",
    "Request failed": "요청 실패",
  };
  return labels[message] ?? message;
}
